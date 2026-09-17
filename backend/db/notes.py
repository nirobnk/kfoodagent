"""CRM notes — the small facts that make the agent feel like it remembers."""

from __future__ import annotations

import logging
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "notes"


async def add(
    *, business_id: str, contact_id: str, note: str, created_by: str = "agent"
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "contact_id": contact_id,
                "note": note.strip(),
                "created_by": created_by,
            }
        )
        .execute()
    )
    saved = first(res)
    log.info("note saved", extra={"contact_id": contact_id, "note": note})
    return saved


async def recent(contact_id: str, limit: int = 5) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("note,created_by,created_at")
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return rows(res)
