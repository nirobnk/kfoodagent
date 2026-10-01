"""Order creation and lookup.

Prices and the delivery fee are recomputed here from the catalogue and the
business profile. Whatever the model believes something costs is ignored — this
is the guard against hallucinated totals.
"""

from __future__ import annotations

import logging
import re

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


def looks_like_an_address(note: str | None) -> bool:
    """Whether a courier could find the customer from this.

    Order #23 went in with "Kadawatha" as its only delivery detail: a town, not
    an address, and nobody asked for the rest. A real one has at least a house
    or street and a town, so it runs to three parts or more; a lone town or
    "Colombo" does not.
    """
    parts = [p for p in re.split(r"[\s,]+", note or "") if p]
    return len(parts) >= 3


async def price_lines(business_id: str, items: list[OrderLine]) -> dict:
    """Price every line from the catalogue and check it against the shelf.

    Shared by quote_order and create_order, so the total a customer is quoted
    is the total the order is created at.
    """
    resolved: list[dict] = []
    unknown: list[str] = []
    short: list[str] = []
    subtotal = 0.0

    for line in items:
        item = await db.menu.get_by_sku(business_id, line.sku)
        if item is None:
            item = await db.menu.get_by_name(business_id, line.sku)
        if item is None:
            unknown.append(line.sku)
            continue

        # The prompt can ask the agent not to sell what is gone; only this can
        # stop it. Stock is counted in singles, so two 5 Packs need ten of them.
        # An untracked product is unlimited, as it was before stock existed.
        single = await db.inventory.single_row(business_id, str(item.get("id")))
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

    profile = await db.business.get_profile(business_id)
    delivery_fee = db.business.delivery_fee_for(profile, subtotal)
    return {
        "resolved": resolved,
        "unknown": unknown,
        "short": short,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "profile": profile,
    }


def totals_line(priced: dict) -> str:
    delivery_fee = priced["delivery_fee"]
    delivery = (
        f"delivery {money(delivery_fee)}"
        if delivery_fee
        else "delivery free (order is over the free-delivery threshold)"
    )
    return f"Items {money(priced['subtotal'])} + {delivery} = total {money(priced['total'])}."


def pricing_problem(priced: dict, *, creating: bool) -> str | None:
    if priced["short"]:
        outcome = "no order was created" if creating else "this cannot be ordered as asked"
        return (
            f"Not enough stock, so {outcome}: "
            + "; ".join(priced["short"])
            + ". Tell the customer honestly what is available, offer the quantity we do "
            "have or a similar product, and only create the order once they agree."
        )
    if priced["unknown"]:
        return (
            "These SKUs are not in the catalogue: "
            + ", ".join(priced["unknown"])
            + ". Call search_menu, confirm the real items with the customer, and do not "
            "create the order yet."
        )
    return None


@tool
async def quote_order(items: list[OrderLine], config: RunnableConfig) -> str:
    """Work out the total for a basket before the customer agrees to it.

    Call this whenever you are about to tell a customer a total. It prices each
    line from the catalogue and applies the delivery fee and the free-delivery
    rule. Quote exactly what it returns; never add a total up yourself.

    Args:
        items: The SKUs and quantities they are asking about.
    """
    ctx = run_context(config)
    ctx.tools_called.append("quote_order")

    if not items:
        return "No items given. Ask the customer what they would like."

    priced = await price_lines(ctx.business_id, items)
    problem = pricing_problem(priced, creating=False)
    if problem:
        return problem

    summary = ", ".join(f"{i['quantity']}x {i['name']}" for i in priced["resolved"])
    return f"Quote (no order created): {summary}. {totals_line(priced)}"


@tool
async def create_order(
    items: list[OrderLine],
    config: RunnableConfig,
    delivery_note: str | None = None,
) -> str:
    """Create an order once the customer has clearly agreed to it.

    Quote back exactly the totals this tool returns — it recalculates every
    price and the delivery fee from the catalogue. Call it once per order.
    It refuses an order with no full delivery address.

    Args:
        items: The SKUs and quantities the customer agreed to.
        delivery_note: Their name and full delivery address (house number or
            name, street or village, town), plus any instruction they gave.
    """
    ctx = run_context(config)
    ctx.tools_called.append("create_order")

    if not items:
        return "No items given. Ask the customer what they would like."

    priced = await price_lines(ctx.business_id, items)
    problem = pricing_problem(priced, creating=True)
    if problem:
        return problem

    if not looks_like_an_address(delivery_note):
        return (
            "No order was created: there is no full delivery address. "
            f"{totals_line(priced)} Tell them this total and, in the same reply, ask for "
            "their name and full delivery address (house number or name, street or "
            "village, town). Create the order once they send it."
        )

    resolved = priced["resolved"]
    subtotal = priced["subtotal"]
    delivery_fee = priced["delivery_fee"]
    total = priced["total"]
    profile = priced["profile"]

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

    return (
        f"Order #{order['order_number']} created: {summary}. "
        f"{totals_line(priced)} Status: new. "
        "Tell the customer the order number and this total. "
        + payment_instruction(profile)
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
