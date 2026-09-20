"""Agent state and per-run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    wa_id: str
    contact: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    recent_notes: list[dict[str, Any]]
    open_order: dict[str, Any] | None
    should_escalate: bool


@dataclass
class RunContext:
    """Side effects a tool performed during one agent run.

    Tools return text to the model; they record structured outcomes here so the
    webhook handler can act on them (escalate, attach an order, log).
    """

    business_id: str
    contact: dict[str, Any]
    escalated: bool = False
    escalation_reason: str | None = None
    created_order: dict[str, Any] | None = None
    # A payment slip the customer sent this turn. The handler uses it to leave
    # the chat with the agent rather than escalating, while still making sure
    # the order is sitting on someone's task list.
    payment_reported: bool = False
    payment_order: dict[str, Any] | None = None
    notes_added: list[str] = field(default_factory=list)
    photos_sent: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)

    @property
    def contact_id(self) -> str:
        return str(self.contact["id"])


def run_context(config: Any) -> RunContext:
    """Pull the RunContext out of a LangGraph RunnableConfig."""
    configurable = (config or {}).get("configurable") or {}
    ctx = configurable.get("run_context")
    if ctx is None:
        raise RuntimeError("run_context missing from config; tools cannot run unbound")
    return ctx
