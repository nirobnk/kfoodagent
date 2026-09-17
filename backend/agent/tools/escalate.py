"""Hand the conversation to a human."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)


@tool
async def escalate_to_human(reason: str, config: RunnableConfig) -> str:
    """Hand this conversation to K-Food staff and stop answering.

    Call this for complaints, refunds, a wrong or missing order, anything about
    money already paid, abuse, or whenever you are not sure of the answer.

    Args:
        reason: One short sentence for staff explaining what the customer needs.
    """
    ctx = run_context(config)
    ctx.tools_called.append("escalate_to_human")

    reason = (reason or "").strip() or "no reason given"
    ctx.escalated = True
    ctx.escalation_reason = reason

    await db.contacts.set_takeover(ctx.business_id, ctx.contact_id, True, by="agent")
    await db.notes.add(
        business_id=ctx.business_id,
        contact_id=ctx.contact_id,
        note=f"Escalated to staff: {reason}",
        created_by="agent",
    )
    log.info("escalated", extra={"contact_id": ctx.contact_id, "reason": reason})

    return (
        "Staff have been notified. Reply once, briefly, telling the customer a "
        "team member will get back to them shortly. Then stop."
    )
