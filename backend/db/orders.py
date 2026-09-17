"""Orders."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "orders"

STATUSES = ("new", "confirmed", "preparing", "dispatched", "delivered", "cancelled")
OPEN_STATUSES = ("new", "confirmed", "preparing", "dispatched")


async def create(
    *,
    business_id: str,
    contact_id: str,
    items: list[dict[str, Any]],
    total: float,
    subtotal: float | None = None,
    delivery_fee: float = 0.0,
    notes: str | None = None,
) -> dict[str, Any]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "contact_id": contact_id,
                "items": items,
                "subtotal": total if subtotal is None else subtotal,
                "delivery_fee": delivery_fee,
                "total": total,
                "notes": notes,
                "status": "new",
            }
        )
        .execute()
    )
    order = first(res)
    if order is None:
        raise RuntimeError("order insert returned no row")
    log.info(
        "order created",
        extra={"order_number": order.get("order_number"), "total": total, "contact_id": contact_id},
    )
    return order


async def get(business_id: str, order_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("id", order_id)
        .limit(1)
        .execute()
    )
    return first(res)


async def latest_for_contact(business_id: str, contact_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return first(res)


async def open_for_contact(business_id: str, contact_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("contact_id", contact_id)
        .in_("status", list(OPEN_STATUSES))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return first(res)


async def set_status(business_id: str, order_id: str, status: str) -> dict[str, Any] | None:
    if status not in STATUSES:
        raise ValueError(f"unknown order status: {status}")
    db = await get_db()
    res = (
        await db.table(TABLE)
        .update({"status": status})
        .eq("business_id", business_id)
        .eq("id", order_id)
        .execute()
    )
    order = first(res)
    if order:
        log.info("order status changed", extra={"order_id": order_id, "status": status})
    return order


async def list_for_business(
    business_id: str,
    *,
    statuses: list[str] | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    db = await get_db()
    query = db.table(TABLE).select("*, contacts(id,name,wa_id)").eq("business_id", business_id)
    if statuses:
        query = query.in_("status", statuses)
    if since:
        query = query.gte("created_at", since.astimezone(timezone.utc).isoformat())
    res = await query.order("created_at", desc=True).limit(limit).execute()
    return rows(res)
