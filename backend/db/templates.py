"""Approved WhatsApp templates and their variable order.

Template names and placeholder order live in the database, not in the code, so
adding or renaming an approved template is a data change.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "templates"


async def get(business_id: str, key: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("key", key)
        .limit(1)
        .execute()
    )
    return first(res)


async def get_approved(business_id: str, key: str) -> dict[str, Any] | None:
    template = await get(business_id, key)
    if template is None:
        log.warning("template missing", extra={"key": key})
        return None
    if not template.get("approved"):
        log.warning("template not approved by Meta yet", extra={"key": key})
        return None
    return template


async def list_all(business_id: str) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .order("key")
        .execute()
    )
    return rows(res)
