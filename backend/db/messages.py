"""Message log. Every inbound and outbound message lands here exactly once."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "messages"


async def exists(wa_message_id: str) -> bool:
    db = await get_db()
    res = await db.table(TABLE).select("id").eq("wa_message_id", wa_message_id).limit(1).execute()
    return bool(rows(res))


async def save(
    *,
    business_id: str,
    contact_id: str,
    direction: str,
    sender: str,
    body: str | None = None,
    media_url: str | None = None,
    message_type: str = "text",
    template_name: str | None = None,
    wa_message_id: str | None = None,
    status: str = "sent",
    error: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Insert a message.

    Idempotent on `wa_message_id`: Meta retries webhook deliveries, so the same
    inbound message arrives more than once. The unique index is the guard and
    this returns None when the row was already there.
    """
    payload: dict[str, Any] = {
        "business_id": business_id,
        "contact_id": contact_id,
        "direction": direction,
        "sender": sender,
        "body": body,
        "media_url": media_url,
        "message_type": message_type,
        "template_name": template_name,
        "wa_message_id": wa_message_id,
        "status": status,
        "error": error,
    }
    if created_at is not None:
        payload["created_at"] = created_at.astimezone(timezone.utc).isoformat()

    db = await get_db()

    if wa_message_id:
        res = (
            await db.table(TABLE)
            .upsert(payload, on_conflict="wa_message_id", ignore_duplicates=True)
            .execute()
        )
        saved = first(res)
        if saved is None:
            log.info("duplicate message ignored", extra={"wa_message_id": wa_message_id})
        return saved

    res = await db.table(TABLE).insert(payload).execute()
    return first(res)


async def update_status(wa_message_id: str, status: str, error: str | None = None) -> None:
    """Apply a delivery receipt. Never downgrades read -> delivered -> sent."""
    rank = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id,status")
        .eq("wa_message_id", wa_message_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    if row is None:
        return
    if rank.get(status, 0) <= rank.get(row.get("status") or "sent", 1) and status != "failed":
        return

    patch: dict[str, Any] = {"status": status}
    if error:
        patch["error"] = error
    await db.table(TABLE).update(patch).eq("id", row["id"]).execute()


async def history(contact_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Last `limit` messages, oldest first — the shape the agent wants."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("direction,sender,body,message_type,created_at")
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(rows(res)))


async def list_for_contact(
    contact_id: str, limit: int = 200, before: str | None = None
) -> list[dict[str, Any]]:
    db = await get_db()
    query = db.table(TABLE).select("*").eq("contact_id", contact_id)
    if before:
        query = query.lt("created_at", before)
    res = await query.order("created_at", desc=True).limit(limit).execute()
    return list(reversed(rows(res)))


async def any_outbound_since(contact_id: str, since: str) -> bool:
    """Has anything gone out to this customer since `since`?

    Used to answer "has this chat been silent since a person took it over?"
    without adding a column to track it: a staff reply, a template, or an
    earlier acknowledgement all count, so the customer is reassured exactly
    once and never talked over.
    """
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id")
        .eq("contact_id", contact_id)
        .eq("direction", "out")
        .gte("created_at", since)
        .limit(1)
        .execute()
    )
    return bool(rows(res))


async def count_since(business_id: str, since: datetime, direction: str = "out") -> int:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id", count="exact")
        .eq("business_id", business_id)
        .eq("direction", direction)
        .gte("created_at", since.astimezone(timezone.utc).isoformat())
        .limit(1)
        .execute()
    )
    return int(res.count or 0)
