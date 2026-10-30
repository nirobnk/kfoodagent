"""Getting a person involved — in the two different senses that means.

For a long time this module had one tool, and it did two jobs badly by doing
them together: it told staff something needed them AND it switched the agent
off. Those are not the same thing, and welding them together is what produced
this, from a real chat:

    customer  Your shop prices are so high
    agent     Sorry to hear that. A staff member will get back to you shortly.
    customer  I need shin red one noodles packet
    agent     —
    customer  Please reply
    agent     —

A price grumble is a sales objection, not a complaint, so it should never have
reached here at all. But the damage was done by the second half: the chat went
into human_takeover, and a customer who was *trying to buy something* got
silence. The shop looked shut.

So there are two tools now, and the name says which is which:

  * `flag_for_staff`  — someone should look at this, and the agent carries on
    serving in the meantime. This is the common case.
  * `escalate_to_human` — a person is taking this conversation over and the
    agent stops. Rare, and only for things a person must own.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)


async def _task(ctx, *, title: str, detail: str, priority: str) -> None:
    """Put it on the shop's list. A failure here must not lose the reply."""
    try:
        await db.crm.create_task(
            business_id=ctx.business_id,
            contact_id=ctx.contact_id,
            title=title,
            detail=detail,
            priority=priority,
            created_by="agent",
        )
    except Exception:
        log.exception("could not create the staff task", extra={"contact_id": ctx.contact_id})


FLAG_TITLE = "Customer needs: "


async def _open_flag(ctx):
    """The task an earlier flag_for_staff left for this customer, if still open."""
    try:
        tasks = await db.crm.list_tasks(ctx.business_id, contact_id=ctx.contact_id)
    except Exception:
        log.warning("could not read open tasks", exc_info=True)
        return None
    return next(
        (t for t in tasks
         if t.get("created_by") == "agent" and (t.get("title") or "").startswith(FLAG_TITLE)),
        None,
    )


async def _refresh_flag(ctx, task, reason: str) -> None:
    """Put the newest ask on the open task. The model restates the whole need
    each time, so the newest reason is the fullest; the old ones stay in the
    detail so nothing asked is lost."""
    detail = (task.get("detail") or "").strip()
    if reason not in detail:
        detail = f"{detail}\n{reason}".strip()
    try:
        await db.crm.update_task(
            ctx.business_id, str(task["id"]), {"title": f"{FLAG_TITLE}{reason}", "detail": detail}
        )
    except Exception:
        log.exception("could not update the staff task", extra={"contact_id": ctx.contact_id})


@tool
async def flag_for_staff(reason: str, config: RunnableConfig) -> str:
    """Put something in front of a person WITHOUT going quiet.

    Use this whenever the customer needs something you cannot do yourself but
    the conversation should carry on: a wholesale or reseller quantity, adding
    to or changing an order that already exists, a delivery date they need
    promised, a special request, a question about the shop you genuinely do
    not have the answer to.

    You keep serving them. Tell them you are getting it sorted and then go on
    answering whatever else they ask — prices, products, a new order. Do NOT
    say they have been passed to someone else, and do not stop replying.

    This is not for anything going wrong. A complaint, a refund, money that
    has gone astray or abuse is `escalate_to_human` instead.

    Args:
        reason: One short sentence telling staff what is needed.
    """
    ctx = run_context(config)
    ctx.tools_called.append("flag_for_staff")

    reason = (reason or "").strip() or "no reason given"
    ctx.flagged = True
    ctx.flag_reason = reason

    waiting = await _open_flag(ctx)
    if waiting is not None:
        # One customer's question about a Saturday delivery became seven tasks on
        # Oct 22, one per reply, and every reply promised again that it was
        # being checked. One task, kept current, and one promise.
        await _refresh_flag(ctx, waiting, reason)
        log.info("already flagged, task updated", extra={"contact_id": ctx.contact_id})
        return (
            "This is already on the shop's list from earlier in this chat, and has been "
            "updated with the latest. You have already told the customer it is being "
            "sorted: do NOT say again that you are checking, sorting or confirming it. "
            "If this message asks about it, say in a few words that it is still being "
            "sorted; otherwise answer only what is new in their message."
        )

    await _task(ctx, title=f"{FLAG_TITLE}{reason}", detail=reason, priority="normal")
    await db.notes.add(
        business_id=ctx.business_id,
        contact_id=ctx.contact_id,
        note=f"Flagged for staff: {reason}",
        created_by="agent",
    )
    log.info("flagged for staff", extra={"contact_id": ctx.contact_id, "reason": reason})

    return (
        "Noted for the shop, and you are still handling this chat. Tell the customer "
        "warmly that you are getting it sorted and will confirm shortly — in your own "
        "voice, without mentioning staff, a team or a handover — and then carry on "
        "answering anything else they ask. Say it this once: later replies do not "
        "repeat it. Do NOT stop replying."
    )


@tool
async def escalate_to_human(reason: str, config: RunnableConfig) -> str:
    """Hand the conversation to a person and STOP replying.

    This switches the agent off for this chat, so the customer gets nothing
    further from you. Only call it when a person must own the conversation:

      * a complaint, or a customer who is upset
      * a refund, or money that has gone wrong — a payment to the wrong
        account, a transfer that did not arrive, a dispute
      * an order that arrived wrong, damaged, late or not at all
      * abuse or threats
      * anything about someone's safety, or a serious allergy question you
        cannot answer exactly from product_details

    Do NOT call it for: a question you simply cannot answer, a wholesale
    enquiry, adding to an order, a request for the bank details, a customer
    grumbling that prices are high, or anything outside the shop's business.
    The first four are `flag_for_staff`. A price grumble is a sales objection
    — answer it. Anything outside the shop is not a task for anyone: decline
    it warmly and move the conversation back to food.

    Args:
        reason: One short sentence for staff explaining what the customer needs.
    """
    ctx = run_context(config)
    ctx.tools_called.append("escalate_to_human")

    reason = (reason or "").strip() or "no reason given"
    ctx.escalated = True
    ctx.escalation_reason = reason

    await db.contacts.set_takeover(ctx.business_id, ctx.contact_id, True, by="agent")
    await _task(ctx, title=f"Take over this chat: {reason}", detail=reason, priority="high")
    await db.notes.add(
        business_id=ctx.business_id,
        contact_id=ctx.contact_id,
        note=f"Escalated to staff: {reason}",
        created_by="agent",
    )
    log.info("escalated", extra={"contact_id": ctx.contact_id, "reason": reason})

    return (
        "This is now in front of a person at the shop, and you are no longer answering "
        "this chat. Reply once, briefly, in your own voice — 'Let me check this properly "
        "and come straight back to you' — and then stop. Do not tell the customer they "
        "have been passed to someone else, and do not mention staff, a team or a "
        "department."
    )
