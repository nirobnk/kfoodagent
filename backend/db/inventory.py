"""Stock, kept as a ledger of movements.

Every change to stock is an append to `inventory_movements`. The quantity on
hand is the sum of those movements, cached on `menu_items.stock_quantity` by a
database trigger, so a wrong number can always be explained by reading the
movements that produced it and repaired with `recompute`.

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
STOCK_FIELDS = "id,sku,product_name,variant_label,category,track_stock,stock_quantity,available"


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
    db = await get_db()
    res = (
        await db.table("menu_items")
        .select("stock_quantity")
        .eq("business_id", business_id)
        .eq("id", menu_item_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    return int((row or {}).get("stock_quantity") or 0)


async def levels(
    business_id: str, *, tracked_only: bool = False, limit: int = 300
) -> list[dict[str, Any]]:
    """Current stock for the catalogue, one row per SKU."""
    db = await get_db()
    query = db.table("menu_items").select(STOCK_FIELDS).eq("business_id", business_id)
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
    """Turn stock tracking on or off for one SKU."""
    db = await get_db()
    res = (
        await db.table("menu_items")
        .update({"track_stock": tracked})
        .eq("business_id", business_id)
        .eq("id", menu_item_id)
        .execute()
    )
    return first(res)


async def sell_order(order: dict[str, Any], *, created_by: str = "system") -> list[str]:
    """Take a confirmed order's items out of stock.

    Safe to call more than once: a unique index allows one 'sold' movement per
    item per order, so an order that goes confirmed -> preparing -> confirmed
    does not sell the same stock twice. Only tracked items move; the rest are
    ignored exactly as they were before stock existed.

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
        quantity_sold = int(item.get("quantity") or 0)
        if not menu_item_id or quantity_sold <= 0:
            continue

        tracked = await _is_tracked(business_id, menu_item_id)
        if not tracked:
            continue

        try:
            await record(
                business_id=business_id,
                menu_item_id=menu_item_id,
                delta=-quantity_sold,
                reason="sold",
                order_id=order_id,
                note=f"order #{order.get('order_number')}",
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


async def _is_tracked(business_id: str, menu_item_id: str) -> bool:
    db = await get_db()
    res = (
        await db.table("menu_items")
        .select("track_stock")
        .eq("business_id", business_id)
        .eq("id", menu_item_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    return bool((row or {}).get("track_stock"))


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
