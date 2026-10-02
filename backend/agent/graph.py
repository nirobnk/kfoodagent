"""The LangGraph agent.

Shape:  load_context -> agent -> (tools -> agent)* -> END

The agent node calls the LLM with tools bound. A conditional edge routes to the
tool node whenever the model asked for a tool, otherwise the run ends and the
last AI message becomes the WhatsApp reply.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

import db
from agent.llm import get_llm
from agent.prompts import FALLBACK_REPLY, build_system_prompt
from agent.state import AgentState, RunContext
from agent.tools import TOOLS
from agent.usage import TokenUsage
from config import settings

log = logging.getLogger(__name__)

# A stop on runaway replies, not a length target. 900 cut the full price list
# mid-line ("Hot Dak Stir-Fry Ramen…") and the customer never saw the rest;
# the full grouped price list (30 products, with emojis) runs to about 2,000.
# WhatsApp allows 4,096.
MAX_REPLY_CHARS = 3500

# An attachment the model cannot open. A caption is readable text, so the
# message reaches the agent — but unlabelled it looks like an ordinary message,
# and "payment done" under a photo of a bank slip then gets answered as chat.
MEDIA_KINDS = {"image", "audio", "video", "document", "voice", "sticker"}


@dataclass(slots=True)
class AgentReply:
    text: str
    escalated: bool = False
    escalation_reason: str | None = None
    flagged: bool = False
    flag_reason: str | None = None
    created_order: dict[str, Any] | None = None
    payment_reported: bool = False
    payment_order: dict[str, Any] | None = None
    tools_called: list[str] = field(default_factory=list)
    failed: bool = False
    usage: TokenUsage | None = None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _to_lc_message(row: Mapping[str, Any]) -> Any:
    body = (row.get("body") or "").strip()
    kind = (row.get("message_type") or "").strip().lower()
    transcript = (row.get("transcript") or "").strip()
    transcription_complete = row.get("transcription_status") == "completed"
    if kind in {"audio", "voice"} and transcript and transcription_complete:
        # Make provenance explicit so the model does not mistake speech-to-text
        # for a caption or claim it heard details that were not transcribed.
        body = f"[{kind} transcript] {transcript}"
    elif (
        kind in {"image", "document"}
        and row.get("direction") == "in"
        and row.get("image_analysis_status") == "completed"
        and (row.get("image_description") or "").strip()
    ):
        # What the photo shows is a model's reading of it, not the customer's
        # words; the caption, when there is one, follows as what they wrote.
        seen = (row.get("image_description") or "").strip()
        label = "image" if kind == "image" else f'document "{row.get("media_filename") or "file"}"'
        body = f"[{label} — what it shows: {seen}]" + (f" Caption: {body}" if body else "")
    elif kind == "document" and row.get("direction") == "in":
        # A file nobody could read: say what it is called, which is often
        # enough ("receipt.pdf", "order list.xlsx").
        name = row.get("media_filename") or "file"
        tail = f" Caption: {body}" if body else " (no caption — you cannot open this, work out what it is)"
        body = f'[document "{name}"]{tail}'
    elif not body:
        # An attachment with no caption. Spelled out rather than left as an
        # empty turn, because the commonest one in this shop is a bank slip
        # sent with no words at all, and the agent has to recognise it as an
        # attachment before it can treat it as one.
        if kind in MEDIA_KINDS and row.get("direction") == "in":
            body = f"[{kind}] (no caption — you cannot open this, work out what it is)"
        else:
            body = f"[{kind or 'media'} message]"
    elif kind in MEDIA_KINDS and row.get("direction") == "in":
        # The caption is all we can read; say so rather than let the agent
        # answer as though it had seen the attachment.
        body = f"[{kind}] {body}"
    if row.get("direction") == "in":
        if row.get("forwarded"):
            body = f"[forwarded] {body}"
        if row.get("reply_to_text"):
            # Swipe-to-reply: "this one" means the message they quoted.
            body = f'[replying to: "{row["reply_to_text"]}"] {body}'
        return HumanMessage(content=body)
    if row.get("sender") == "human":
        return AIMessage(content=f"(staff) {body}")
    return AIMessage(content=body)


async def load_context(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Load just enough history: last N turns, up to M notes, the open order."""
    configurable = (config or {}).get("configurable") or {}
    ctx: RunContext = configurable["run_context"]
    business_name: str = configurable.get("business_name") or "K-Food"
    incoming: str = configurable.get("incoming_text") or ""

    contact = ctx.contact
    history = await db.messages.history(ctx.contact_id, limit=settings.history_turns)
    notes = await db.notes.recent(ctx.contact_id, limit=settings.notes_limit)
    open_order = await db.orders.open_for_contact(ctx.business_id, ctx.contact_id)
    profile = await db.business.get_profile(ctx.business_id)

    system = SystemMessage(
        content=build_system_prompt(
            business_name=business_name,
            contact=contact,
            profile=profile,
            notes=notes,
            open_order=open_order,
        )
    )

    conversation = [
        _to_lc_message(row) for row in history if row.get("message_type") != "reaction"
    ]

    # The inbound message is already in the database by the time the agent
    # runs, so only append it when history did not pick it up.
    last_inbound = next(
        (row for row in reversed(history) if row.get("direction") == "in"), None
    )
    if incoming and (last_inbound is None or (last_inbound.get("body") or "").strip() != incoming.strip()):
        conversation.append(HumanMessage(content=incoming))

    if not conversation:
        conversation.append(HumanMessage(content=incoming or "Hello"))

    return {
        "wa_id": contact.get("wa_id"),
        "contact": dict(contact),
        "messages": [system, *conversation],
        "recent_notes": notes,
        "open_order": open_order,
        "should_escalate": False,
    }


@lru_cache(maxsize=1)
def _llm_with_tools() -> Any:
    return get_llm().bind_tools(TOOLS)


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    messages = state.get("messages") or []
    response = await _llm_with_tools().ainvoke(messages, config)
    ctx = ((config or {}).get("configurable") or {}).get("run_context")
    if ctx is not None:
        ctx.usage.add(response)
    return {"messages": [response]}


def route(state: AgentState) -> str:
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return END


@lru_cache(maxsize=1)
def build_graph() -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def clean_reply(text: str) -> str:
    """WhatsApp has no markdown headings or bullets. Strip what the model adds."""
    text = (text or "").strip()
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.DOTALL)   # bold -> WhatsApp bold
    text = re.sub(r"^\s*[-*•]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > MAX_REPLY_CHARS:
        cut = text[:MAX_REPLY_CHARS]
        text = cut.rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def _extract_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content blocks
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") in (None, "text")
        ]
        return "\n".join(p for p in parts if p)
    return str(content or "")


async def run_agent(
    *,
    business_id: str,
    contact: Mapping[str, Any],
    incoming_text: str,
    business_name: str | None = None,
) -> AgentReply:
    """Run one turn of the agent and return the single reply to send."""
    ctx = RunContext(business_id=business_id, contact=dict(contact))
    if business_name is None:
        try:
            business_name = await db.business.get_name(business_id)
        except Exception:
            log.warning("could not read the business name", exc_info=True)
            business_name = "K FOOD"
    config = {
        "configurable": {
            "run_context": ctx,
            "business_name": business_name,
            "incoming_text": incoming_text,
            "thread_id": str(contact.get("id")),
        },
        "recursion_limit": max(4, settings.llm_max_tool_loops * 2 + 2),
    }

    try:
        result = await build_graph().ainvoke({}, config)
    except Exception as exc:
        log.exception(
            "agent run failed",
            extra={"contact_id": contact.get("id"), "wa_id": contact.get("wa_id"), "error": str(exc)},
        )
        # Nobody should be left without an answer: hand it to a human.
        if not ctx.escalated:
            try:
                await db.contacts.set_takeover(business_id, str(contact["id"]), True, by="agent")
                ctx.escalated = True
                ctx.escalation_reason = "agent error"
            except Exception:
                log.exception("failed to escalate after agent error")
        return AgentReply(
            text=FALLBACK_REPLY,
            escalated=ctx.escalated,
            escalation_reason=ctx.escalation_reason,
            tools_called=ctx.tools_called,
            failed=True,
            usage=ctx.usage,
        )

    messages = result.get("messages") or []
    reply_text = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            reply_text = _extract_text(message)
            if reply_text.strip():
                break

    reply_text = clean_reply(reply_text)
    if not reply_text:
        log.warning("agent produced no text", extra={"contact_id": contact.get("id")})
        reply_text = FALLBACK_REPLY

    log.info(
        "agent turn complete",
        extra={
            "contact_id": contact.get("id"),
            "tools": ctx.tools_called,
            "escalated": ctx.escalated,
            "reply_chars": len(reply_text),
            "llm_calls": ctx.usage.calls,
            "input_tokens": ctx.usage.input_tokens,
            "cache_write_tokens": ctx.usage.cache_write_tokens,
            "output_tokens": ctx.usage.output_tokens,
            "cost_usd": ctx.usage.cost_usd(),
        },
    )

    return AgentReply(
        text=reply_text,
        escalated=ctx.escalated,
        escalation_reason=ctx.escalation_reason,
        flagged=ctx.flagged,
        flag_reason=ctx.flag_reason,
        created_order=ctx.created_order,
        payment_reported=ctx.payment_reported,
        payment_order=ctx.payment_order,
        tools_called=ctx.tools_called,
        usage=ctx.usage,
    )
