"""Order creation and lookup.

Prices and the delivery fee are recomputed here from the catalogue and the
business profile. Whatever the model believes something costs is ignored — this
is the guard against hallucinated totals.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

import db
from agent.state import run_context
from agent.tools.payments import bank_block

log = logging.getLogger(__name__)


class OrderLine(BaseModel):
    sku: str = Field(
        description="The SKU in square brackets from search_menu, e.g. RAM-SHIN-5. "
        "It identifies both the product and the pack size."
    )
    quantity: int = Field(default=1, ge=1, le=50, description="How many of this SKU")


def money(value: float) -> str:
    return f"Rs. {value:,.0f}"


def payment_instruction(profile: dict) -> str:
    """What to tell the customer about paying, with the details in hand.

    The account number is printed on the shop's own checkout page, so making a
    customer who has just ordered wait for a human to send it only loses the
    sale. Carrying it back here saves a second tool call, and stops the reply
    ending on "the bank details will follow shortly".

    The block is the same one `payment_details` returns, laid out line by line
    so the customer can copy the account number straight out of the message.
    """
    block = bank_block(profile)
    if not block:
        return (
            "Tell them you will send the bank details in a moment, and call "
            "escalate_to_human."
        )
    return (
        "In the SAME reply, send them these bank details exactly as laid out here, "
        "on their own lines, so they can pay now:\n"
        f"{block}\n"
        "Then ask them, warmly, to send the payment receipt here once they have "
        "transferred it, and say you will confirm stock and get it moving."
    )


@tool
async def create_order(
    items: list[OrderLine],
    config: RunnableConfig,
    delivery_note: str | None = None,
) -> str:
    """Create an order once the customer has clearly agreed to it.

    Quote back exactly the totals this tool returns — it recalculates every
    price and the delivery fee from the catalogue. Call it once per order.

    Args:
        items: The SKUs and quantities the customer agreed to.
        delivery_note: The delivery address and any instruction the customer gave.
    """
    ctx = run_context(config)
    ctx.tools_called.append("create_order")

    if not items:
        return "No items given. Ask the customer what they would like."

    resolved: list[dict] = []
    unknown: list[str] = []
    short: list[str] = []
    subtotal = 0.0

    for line in items:
        item = await db.menu.get_by_sku(ctx.business_id, line.sku)
        if item is None:
            item = await db.menu.get_by_name(ctx.business_id, line.sku)
        if item is None:
            unknown.append(line.sku)
            continue

        # The prompt can ask the agent not to sell what is gone; only this can
        # stop it. Stock is counted in singles, so two 5 Packs need ten of them.
        # An untracked product is unlimited, as it was before stock existed.
        single = await db.inventory.single_row(ctx.business_id, str(item.get("id")))
        if single is not None and single.get("track_stock"):
            per_pack = max(1, int(item.get("units") or 1))
            singles_needed = line.quantity * per_pack
            on_hand = int(single.get("stock_quantity") or 0)
            if on_hand < singles_needed:
                asked = (
                    f"{line.quantity} x {item.get('variant_label') or 'unit'}"
                    f" ({singles_needed} singles)"
                    if per_pack > 1
                    else f"{line.quantity}"
                )
                short.append(
                    f"{item.get('product_name') or line.sku}: asked for {asked}, "
                    f"{on_hand} singles in stock"
                )
                continue

        price = float(item.get("price") or 0)
        line_total = price * line.quantity
        subtotal += line_total
        resolved.append(
            {
                "sku": item.get("sku"),
                "menu_item_id": item.get("id"),
                "name": item.get("name"),
                "product": item.get("product_name"),
                "variant": item.get("variant_label"),
                "quantity": line.quantity,
                "unit_price": price,
                "subtotal": line_total,
            }
        )

    if short:
        return (
            "Not enough stock, so no order was created: "
            + "; ".join(short)
            + ". Tell the customer honestly what is available, offer the quantity we do "
            "have or a similar product, and only create the order once they agree."
        )

    if unknown:
        return (
            "These SKUs are not in the catalogue: "
            + ", ".join(unknown)
            + ". Call search_menu, confirm the real items with the customer, and do not "
            "create the order yet."
        )

    profile = await db.business.get_profile(ctx.business_id)
    delivery_fee = db.business.delivery_fee_for(profile, subtotal)
    total = subtotal + delivery_fee

    order = await db.orders.create(
        business_id=ctx.business_id,
        contact_id=ctx.contact_id,
        items=resolved,
        subtotal=round(subtotal, 2),
        delivery_fee=round(delivery_fee, 2),
        total=round(total, 2),
        notes=delivery_note,
    )
    ctx.created_order = order

    summary = ", ".join(f"{i['quantity']}x {i['name']}" for i in resolved)
    delivery_line = (
        f"delivery {money(delivery_fee)}"
        if delivery_fee
        else "delivery free (order is over the free-delivery threshold)"
    )
    address_line = "" if delivery_note else " Ask for the delivery address if you do not have it."

    return (
        f"Order #{order['order_number']} created: {summary}. "
        f"Items {money(subtotal)} + {delivery_line} = total {money(total)}. Status: new. "
        "Tell the customer the order number and this total. "
        + payment_instruction(profile)
        + address_line
    )


@tool
async def check_order_status(config: RunnableConfig) -> str:
    """Look up this customer's most recent order and its current status."""
    ctx = run_context(config)
    ctx.tools_called.append("check_order_status")

    order = await db.orders.latest_for_contact(ctx.business_id, ctx.contact_id)
    if order is None:
        return "This customer has no orders yet."

    items = order.get("items") or []
    summary = ", ".join(
        f"{i.get('quantity', 1)}x {i.get('name')}" for i in items if isinstance(i, dict)
    )
    total = float(order.get("total") or 0)
    delivery_fee = float(order.get("delivery_fee") or 0)
    return (
        f"Order #{order['order_number']} — status: {order['status']}. "
        f"Items: {summary or 'none recorded'}. "
        f"Total {money(total)} (includes {money(delivery_fee)} delivery). "
        f"Placed: {order.get('created_at')}."
    )
