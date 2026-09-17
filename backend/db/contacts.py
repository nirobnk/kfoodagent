"""Contacts: one row per customer phone number, per business."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "contacts"


async def get_by_wa_id(business_id: str, wa_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("wa_id", wa_id)
        .limit(1)
        .execute()
    )
    return first(res)


async def get_by_id(business_id: str, contact_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("id", contact_id)
        .limit(1)
        .execute()
    )
    return first(res)


async def get_or_create(
    business_id: str, wa_id: str, name: str | None = None
) -> dict[str, Any]:
    """Fetch the contact, creating it on first contact.

    Safe against the race where two webhook deliveries arrive together: the
    unique (business_id, wa_id) index turns the loser into a re-read.
    """
    existing = await get_by_wa_id(business_id, wa_id)
    if existing:
        if name and not existing.get("name"):
            existing = await update(business_id, existing["id"], {"name": name}) or existing
        return existing

    db = await get_db()
    try:
        res = (
            await db.table(TABLE)
            .insert({"business_id": business_id, "wa_id": wa_id, "name": name})
            .execute()
        )
        created = first(res)
        if created:
            log.info("contact created", extra={"wa_id": wa_id, "contact_id": created["id"]})
            return created
    except Exception as exc:  # unique violation from a concurrent insert
        log.warning("contact insert raced, re-reading", extra={"wa_id": wa_id, "error": str(exc)})

    contact = await get_by_wa_id(business_id, wa_id)
    if contact is None:
        raise RuntimeError(f"could not create or read contact {wa_id}")
    return contact


async def update(
    business_id: str, contact_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .update(patch)
        .eq("business_id", business_id)
        .eq("id", contact_id)
        .execute()
    )
    return first(res)


async def touch_inbound(
    business_id: str, contact_id: str, *, at: datetime | None = None, name: str | None = None
) -> dict[str, Any] | None:
    """Record that the customer just messaged us.

    This is what opens the 24-hour free-text window, so it runs on every
    inbound message, before the agent does anything.
    """
    stamp = (at or datetime.now(timezone.utc)).isoformat()
    patch: dict[str, Any] = {"last_seen": stamp, "last_customer_message_at": stamp}
    if name:
        patch["name"] = name
    return await update(business_id, contact_id, patch)


async def bump_unread(business_id: str, contact_id: str) -> None:
    db = await get_db()
    try:
        await db.rpc("bump_unread", {"p_contact_id": contact_id}).execute()
    except Exception as exc:
        log.warning("bump_unread failed", extra={"contact_id": contact_id, "error": str(exc)})


async def mark_read(business_id: str, contact_id: str) -> dict[str, Any] | None:
    return await update(business_id, contact_id, {"unread_count": 0})


async def set_takeover(
    business_id: str, contact_id: str, enabled: bool, by: str | None = None
) -> dict[str, Any] | None:
    patch: dict[str, Any] = {"human_takeover": enabled}
    if enabled:
        patch["takeover_started_at"] = datetime.now(timezone.utc).isoformat()
        patch["takeover_by"] = by
    else:
        patch["takeover_started_at"] = None
        patch["takeover_by"] = None
    contact = await update(business_id, contact_id, patch)
    log.info(
        "takeover changed",
        extra={"contact_id": contact_id, "human_takeover": enabled, "by": by},
    )
    return contact


async def expire_takeovers(business_id: str, minutes: int) -> list[dict[str, Any]]:
    """Hand control back to the agent after `minutes` of human silence.

    Without this, staff forget to switch back and customers get silence.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    db = await get_db()
    res = (
        await db.table(TABLE)
        .update({"human_takeover": False, "takeover_started_at": None, "takeover_by": None})
        .eq("business_id", business_id)
        .eq("human_takeover", True)
        .lt("takeover_started_at", cutoff)
        .execute()
    )
    reverted = rows(res)
    if reverted:
        log.info(
            "takeover auto-returned",
            extra={"count": len(reverted), "contact_ids": [c["id"] for c in reverted]},
        )
    return reverted


async def list_recent(business_id: str, limit: int = 100) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .order("last_seen", desc=True)
        .limit(limit)
        .execute()
    )
    return rows(res)
