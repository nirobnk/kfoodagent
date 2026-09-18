"""Stock, kept as a ledger of movements.

Every change to stock is an append to `inventory_movements`. The quantity on
hand is the sum of those movements, cached on `menu_items.stock_quantity` by a
database trigger, so a wrong number can always be explained by reading the
movements that produced it and repaired with `recompute`.

Stock is counted in SINGLE UNITS, once per product, and held on that product's
single-unit row. A 5 Pack and a carton of 20 are not separate things on a
shelf: staff make them up from singles when a customer orders one, so selling
a 5 Pack takes five singles and a carton takes twenty. Entering 100 means one
hundred single units of that product, whatever pack a customer buys it in.

Nothing here decides policy: whether a product is tracked at all is
`menu_items.track_stock`, and an untracked product behaves exactly as it did
before stock existed — unlimited.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "inventory_movements"

# A movement's reason is not decoration: it is how a stocktake discrepancy gets
# explained later. These match the check constraint in 0005_inventory.sql.
REASONS = ("received", "sold", "returned", "damaged", "expired", "adjusted", "count")

# Reasons a human may record from the dashboard. 'sold' is excluded on purpose:
# a sale comes from an order being confirmed, never from someone typing it.
STAFF_REASONS = ("received", "returned", "damaged", "expired", "adjusted", "count")

MOVEMENT_FIELDS = "id,menu_item_id,delta,reason,order_id,note,created_by,created_at"
STOCK_FIELDS = (
    "id,sku,handle,units,product_name,variant_label,category,"
    "track_stock,stock_quantity,available"
)


async def single_row(business_id: str, menu_item_id: str) -> dict[str, Any] | None:
    """The row that holds a product's stock: its single-unit variant.

    Given any variant — a 5 Pack, a carton — this returns the single of the
    same product, because stock is counted in singles and only there. Every
    product in the catalogue has one.
    """
    db = await get_db()
    res = (
        await db.table("menu_items")
        .select("id,handle,units,track_stock,stock_quantity,sku,product_name,variant_label")
        .eq("business_id", business_id)
        .eq("id", menu_item_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    if row is None:
        return None
    if int(row.get("units") or 1) == 1:
        return row

    res = (
        await db.table("menu_items")
        .select("id,handle,units,track_stock,stock_quantity,sku,product_name,variant_label")
        .eq("business_id", business_id)
        .eq("handle", row.get("handle"))
        .eq("units", 1)
        .limit(1)
        .execute()
    )
    # Falling back to the variant itself keeps a malformed catalogue working
    # rather than silently losing the movement.
    return first(res) or row


async def record(
    *,
    business_id: str,
    menu_item_id: str,
    delta: int,
    reason: str,
    order_id: str | None = None,
    note: str | None = None,
    created_by: str = "system",
) -> dict[str, Any] | None:
    """Append one movement. The trigger updates the cached quantity."""
    if reason not in REASONS:
        raise ValueError(f"unknown inventory reason: {reason}")
    if delta == 0:
        raise ValueError("a movement of zero changes nothing; it is a note, not a movement")

    # Stock lives on the single. A movement aimed at a 5 Pack is really about
    # the singles that make it up.
    single = await single_row(business_id, menu_item_id)
    if single is not None:
        menu_item_id = str(single["id"])

    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "menu_item_id": menu_item_id,
                "delta": int(delta),
                "reason": reason,
                "order_id": order_id,
                "note": (note or "").strip() or None,
                "created_by": created_by,
            }
        )
        .execute()
    )
    saved = first(res)
    log.info(
        "stock movement",
        extra={"menu_item_id": menu_item_id, "delta": delta, "reason": reason},
    )
    return saved


async def set_count(
    *,
    business_id: str,
    menu_item_id: str,
    counted: int,
    created_by: str = "staff",
    note: str | None = None,
) -> dict[str, Any] | None:
    """Record a stocktake: what is actually on the shelf right now.

    Stored as the difference from the current figure, so the ledger keeps
    saying how stock changed rather than quietly overwriting history. A count
    that matches records nothing, because nothing moved.
    """
    current = await quantity(business_id, menu_item_id)
    delta = int(counted) - current
    if delta == 0:
        return None
    return await record(
        business_id=business_id,
        menu_item_id=menu_item_id,
        delta=delta,
        reason="count",
        note=note or f"stocktake: counted {counted}, system said {current}",
        created_by=created_by,
    )


async def quantity(business_id: str, menu_item_id: str) -> int:
    """Singles on hand for this product, whichever variant is named."""
    single = await single_row(business_id, menu_item_id)
    return int((single or {}).get("stock_quantity") or 0)


async def levels(
    business_id: str, *, tracked_only: bool = False, limit: int = 300
) -> list[dict[str, Any]]:
    """Current stock for the catalogue, one row per SKU."""
    db = await get_db()
    query = (
        db.table("menu_items")
        .select(STOCK_FIELDS)
        .eq("business_id", business_id)
        # One row per product. The 5 Pack and the carton are made from these.
        .eq("units", 1)
    )
    if tracked_only:
        query = query.eq("track_stock", True)
    res = await query.order("sort_order").limit(limit).execute()
    return rows(res)


async def movements(
    business_id: str, *, menu_item_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """The ledger, newest first — why the number is what it is."""
    db = await get_db()
    query = db.table(TABLE).select(MOVEMENT_FIELDS).eq("business_id", business_id)
    if menu_item_id:
        query = query.eq("menu_item_id", menu_item_id)
    res = await query.order("created_at", desc=True).limit(limit).execute()
    return rows(res)


async def set_tracking(
    business_id: str, menu_item_id: str, tracked: bool
) -> dict[str, Any] | None:
    """Turn stock tracking on or off for a product.

    The flag lives on the single with the count, so naming any variant turns it
    on for the product as a whole.
    """
    single = await single_row(business_id, menu_item_id)
    target = str((single or {}).get("id") or menu_item_id)
    db = await get_db()
    res = (
        await db.table("menu_items")
        .update({"track_stock": tracked})
        .eq("business_id", business_id)
        .eq("id", target)
        .execute()
    )
    return first(res)


async def sell_order(order: dict[str, Any], *, created_by: str = "system") -> list[str]:
    """Take a confirmed order's items out of stock, counted in singles.

    A line for two 5 Packs removes ten singles, because that is what staff take
    off the shelf to make them up. Safe to call more than once: a unique index
    allows one 'sold' movement per item per order, so an order that goes
    confirmed -> preparing -> confirmed does not sell the same stock twice.
    Only tracked products move; the rest are ignored exactly as they were
    before stock existed.

    Returns the SKUs that were decremented.
    """
    business_id = order.get("business_id")
    order_id = order.get("id")
    items = order.get("items") or []
    if not business_id or not order_id or not items:
        return []

    sold: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        menu_item_id = item.get("menu_item_id")
        packs_sold = int(item.get("quantity") or 0)
        if not menu_item_id or packs_sold <= 0:
            continue

        single = await single_row(business_id, menu_item_id)
        if single is None or not single.get("track_stock"):
            continue

        # How many singles this line actually removes from the shelf.
        per_pack = await units_in(business_id, menu_item_id)
        singles_sold = packs_sold * per_pack
        note = f"order #{order.get('order_number')}"
        if per_pack > 1:
            note += f" — {packs_sold} x {per_pack}"

        try:
            await record(
                business_id=business_id,
                menu_item_id=str(single["id"]),
                delta=-singles_sold,
                reason="sold",
                order_id=order_id,
                note=note,
                created_by=created_by,
            )
            sold.append(str(item.get("sku") or menu_item_id))
        except Exception as exc:
            # The unique index rejecting a repeat is the guard working, not a
            # failure. Anything else is worth seeing, but must never stop an
            # order from progressing.
            log.info(
                "stock not decremented",
                extra={"order_id": order_id, "sku": item.get("sku"), "error": str(exc)[:200]},
            )
    return sold


async def restock_order(order: dict[str, Any], *, created_by: str = "system") -> list[str]:
    """Put a cancelled order's stock back.

    Only reverses what was actually taken: it reads the 'sold' movements for
    this order rather than trusting the order lines, so a partially sold order
    comes back partially. Idempotent — an order already put back is left alone,
    because cancelling twice must not invent stock.

    Returns the menu_item_ids that were restored.
    """
    business_id = order.get("business_id")
    order_id = order.get("id")
    if not business_id or not order_id:
        return []

    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("menu_item_id,delta,reason")
        .eq("business_id", business_id)
        .eq("order_id", order_id)
        .execute()
    )
    history = rows(res)

    already_back = {r["menu_item_id"] for r in history if r.get("reason") == "returned"}
    restored: list[str] = []
    for movement in history:
        if movement.get("reason") != "sold":
            continue
        item_id = movement["menu_item_id"]
        if item_id in already_back:
            continue
        await record(
            business_id=business_id,
            menu_item_id=item_id,
            delta=-int(movement["delta"]),  # the sale was negative; put it back
            reason="returned",
            order_id=order_id,
            note=f"order #{order.get('order_number')} cancelled",
            created_by=created_by,
        )
        restored.append(item_id)
    return restored


async def units_in(business_id: str, menu_item_id: str) -> int:
    """How many singles one of this variant contains: 1, 5 or 20."""
    db = await get_db()
    res = (
        await db.table("menu_items")
        .select("units")
        .eq("business_id", business_id)
        .eq("id", menu_item_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    return max(1, int((row or {}).get("units") or 1))


async def recompute(business_id: str) -> int:
    """Rebuild every cached quantity from the ledger. Returns rows corrected."""
    db = await get_db()
    res = await db.rpc("recompute_stock", {"p_business_id": business_id}).execute()
    data = getattr(res, "data", None)
    if isinstance(data, list) and data:
        first_row = data[0]
        if isinstance(first_row, dict):
            return int(next(iter(first_row.values()), 0) or 0)
        return int(first_row or 0)
    return int(data or 0)
