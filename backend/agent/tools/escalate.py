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
    """Put this conversation in front of a person at the shop and stop answering.

    Call this for complaints, refunds, a wrong, missing or damaged order, a
    payment that has gone wrong, abuse, wholesale enquiries, or whenever you
    are genuinely unsure of the answer. Asking for the bank details is not a
    reason to call it.

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
        "This is now in front of a person at the shop. Reply once, briefly, in your "
        "own voice — 'Let me check this properly and come straight back to you' — and "
        "then stop. Do not tell the customer they have been passed to someone else, "
        "and do not mention staff, a team or a department."
    )
