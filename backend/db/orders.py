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
    discount: float = 0.0,
    discount_note: str | None = None,
    source: str = "agent",
    external_ref: str | None = None,
) -> dict[str, Any]:
    """Insert an order.

    `source` records which surface created it and `external_ref` is the POS bill
    number, which the partial unique index turns into an idempotency key: a
    retried outbox entry raises here rather than creating a second order.
    """
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
                "discount": discount,
                "discount_note": discount_note,
                "total": total,
                "notes": notes,
                "status": "new",
                "source": source,
                "external_ref": external_ref,
            }
        )
        .execute()
    )
    order = first(res)
    if order is None:
        raise RuntimeError("order insert returned no row")
    log.info(
        "order created",
        extra={"order_number": order.get("order_number"), "total": total,
               "contact_id": contact_id, "source": source},
    )
    return order


async def get_by_external_ref(business_id: str, external_ref: str) -> dict[str, Any] | None:
    """Find the order a POS bill already created, if it did."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("external_ref", external_ref)
        .limit(1)
        .execute()
    )
    return first(res)


async def append_note(business_id: str, order_id: str, line: str) -> dict[str, Any] | None:
    """Add a line to an order's notes without losing what is there.

    Used to record a price mismatch in words, where staff will actually read it.
    """
    existing = await get(business_id, order_id)
    if existing is None:
        return None
    current = (existing.get("notes") or "").strip()
    combined = f"{current}\n{line}".strip() if current else line

    db = await get_db()
    res = (
        await db.table(TABLE)
        .update({"notes": combined})
        .eq("business_id", business_id)
        .eq("id", order_id)
        .execute()
    )
    return first(res)


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


async def list_for_pos(
    business_id: str,
    *,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Orders with their customer attached, for printing an invoice.

    Deliberately NOT `list_for_business`, which uses PostgREST's FK embedding
    (`select("*, contacts(...)")`). The test fake ignores embedding entirely, so
    a test written against that would pass happily on a payload with no customer
    on it — and the POS would print a nameless invoice in production. Two plain
    queries cost one extra round trip and can actually be tested.
    """
    db = await get_db()
    query = db.table(TABLE).select("*").eq("business_id", business_id)
    if statuses:
        query = query.in_("status", statuses)
    res = await query.order("created_at", desc=True).limit(limit).execute()
    orders = rows(res)
    if not orders:
        return []

    contact_ids = list({str(o["contact_id"]) for o in orders if o.get("contact_id")})
    contacts: dict[str, dict[str, Any]] = {}
    if contact_ids:
        found = await db.table("contacts").select("*").in_("id", contact_ids).execute()
        contacts = {str(c["id"]): c for c in rows(found)}

    for order in orders:
        order["contact"] = contacts.get(str(order.get("contact_id")))
    return orders
