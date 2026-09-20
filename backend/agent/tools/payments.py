"""Money: giving out the bank details, and taking in a receipt.

Two things a shop assistant does all day and the agent could not do at all.
Before this, "how do I pay?" went through `store_info`, which returns a
paragraph of prose the model then had to reassemble into something a customer
could read and copy — and it reassembled it differently every time, sometimes
dropping a digit of the account number. `payment_details` returns the block
already laid out, so the model's only job is to paste it.

`record_payment_receipt` is the other half. A customer who has paid sends a
screenshot, and the agent cannot open it. What it can do is exactly what a
person at the counter does with a slip they have not checked yet: take it,
write it down, say thank you, and promise a confirmation once it is checked.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)


def money(value: float | int | str | None) -> str:
    try:
        return f"Rs. {float(value):,.0f}"
    except (TypeError, ValueError):
        return f"Rs. {value}"


def bank_block(profile: dict, *, amount: float | None = None) -> str:
    """The bank details laid out the way they should reach the customer.

    One fact per line, no prose between them: a customer copies the account
    number out of this straight into their banking app, and a number wrapped
    in a sentence is a number that gets copied wrong.
    """
    bank = ((profile or {}).get("payment") or {}).get("bankDetails") or {}
    if not bank.get("accountNumber"):
        return ""

    lines = [
        "Bank: " + str(bank.get("bank") or ""),
        "Branch: " + str(bank.get("branch") or ""),
        "Account name: " + str(bank.get("accountName") or ""),
        "Account number: " + str(bank.get("accountNumber") or ""),
    ]
    if amount is not None:
        lines.append(f"Amount: {money(amount)}")
    return "\n".join(line for line in lines if line.split(": ", 1)[-1])


@tool
async def payment_details(config: RunnableConfig) -> str:
    """Get the shop's bank details, laid out ready to send to the customer.

    Call this whenever someone asks how to pay, for the bank account, the
    account number, or where to send the money — and always right after
    creating an order, so they can pay without asking. Bank transfer is the
    only way to pay; there is no card payment and no cash on delivery.

    The block comes back already formatted. Send it exactly as it is, on its
    own lines. Do not rewrite it into a sentence and never retype the account
    number from memory.
    """
    ctx = run_context(config)
    ctx.tools_called.append("payment_details")

    profile = await db.business.get_profile(ctx.business_id)
    order = await db.orders.awaiting_payment(ctx.business_id, ctx.contact_id)
    amount = float(order["total"]) if order and order.get("total") is not None else None

    block = bank_block(profile, amount=amount)
    if not block:
        return (
            "The bank details are not on file. Tell the customer you will send "
            "them in a moment, and call escalate_to_human."
        )

    lines = ["Send this block to the customer exactly as written, on its own lines:", block]
    if order:
        lines.append(
            f"This is for order #{order.get('order_number')}, total {money(order.get('total'))}."
        )
    lines.append(
        "Then ask them to send the payment receipt here once they have transferred it. "
        "Bank transfer is the only payment method — no card, no cash on delivery."
    )
    log.info("tool payment_details", extra={"has_order": bool(order)})
    return "\n".join(lines)


@tool
async def record_payment_receipt(
    config: RunnableConfig,
    what_they_sent: str,
    amount: float | None = None,
    reference: str | None = None,
) -> str:
    """Record that the customer has paid or sent a payment slip.

    Call this the moment a customer says they have transferred the money, or
    sends an image right after you gave them the bank details — that image is
    almost always the slip. Call it once per payment.

    You cannot see the image, so never tell the customer the payment is
    confirmed or received in the account. Thank them, say you will check it
    and confirm shortly, and leave it there. The order is flagged for checking
    the moment you call this.

    Args:
        what_they_sent: One short line for the shop's records — "bank slip
            screenshot", "says paid Rs. 4,050 by HNB transfer".
        amount: The amount they said they paid, if they said one.
        reference: A transaction reference or the bank they paid from, if given.
    """
    ctx = run_context(config)
    ctx.tools_called.append("record_payment_receipt")

    detail = (what_they_sent or "").strip() or "payment slip sent on WhatsApp"
    if amount is not None:
        detail += f" — amount stated {money(amount)}"
    if reference:
        detail += f" — reference {reference.strip()}"

    order = await db.orders.awaiting_payment(ctx.business_id, ctx.contact_id)
    if order is None:
        order = await db.orders.latest_for_contact(ctx.business_id, ctx.contact_id)

    if order is None:
        # Paid before ordering, or paid for something arranged off WhatsApp.
        # Still worth a human's eyes; there is just no order to hang it on.
        await db.notes.add(
            business_id=ctx.business_id,
            contact_id=ctx.contact_id,
            note=f"Says they paid, but has no order on file: {detail}",
            created_by="agent",
        )
        await _task(ctx, title="Payment with no order — check it", detail=detail)
        ctx.payment_reported = True
        return (
            "Recorded, and flagged for checking. There is no order on file for this "
            "customer, so ask them warmly what they ordered and who they arranged it "
            "with, and say you will confirm as soon as it is checked. Do not say the "
            "payment has been received."
        )

    order_id = str(order["id"])
    updated = await db.orders.mark_receipt_received(ctx.business_id, order_id, note=detail)
    await _task(
        ctx,
        title=f"Check payment for order #{order.get('order_number')}",
        detail=f"{detail}. Order total {money(order.get('total'))}.",
        order_id=order_id,
    )
    await db.notes.add(
        business_id=ctx.business_id,
        contact_id=ctx.contact_id,
        note=f"Payment reported for order #{order.get('order_number')}: {detail}",
        created_by="agent",
    )

    ctx.payment_reported = True
    ctx.payment_order = updated or order
    log.info(
        "payment receipt recorded",
        extra={"order_number": order.get("order_number"), "contact_id": ctx.contact_id},
    )

    return (
        f"Recorded against order #{order.get('order_number')} "
        f"(total {money(order.get('total'))}) and flagged for checking. "
        "Thank them warmly in one short line, say you will check it and confirm shortly, "
        "and tell them the order goes out once it is confirmed. Do NOT say the payment "
        "has been received or verified — you have not seen it."
    )


async def _task(ctx, *, title: str, detail: str, order_id: str | None = None) -> None:
    """Put it on the shop's task list. A failure here must not lose the reply."""
    try:
        await db.crm.create_task(
            business_id=ctx.business_id,
            contact_id=ctx.contact_id,
            order_id=order_id,
            title=title,
            detail=detail,
            priority="high",
            created_by="agent",
        )
    except Exception:
        log.exception("could not create the payment task", extra={"contact_id": ctx.contact_id})
