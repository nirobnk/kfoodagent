"""What each agent reply cost: tokens by kind, and dollars."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "llm_usage"


async def record(
    *,
    business_id: str,
    contact_id: str | None,
    usage: dict[str, Any],
    reply_wa_message_id: str | None = None,
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "contact_id": contact_id,
                "reply_wa_message_id": reply_wa_message_id,
                "model": usage.get("model"),
                "calls": usage.get("calls") or 0,
                "input_tokens": usage.get("input_tokens") or 0,
                "cached_tokens": usage.get("cached_tokens") or 0,
                "cache_write_tokens": usage.get("cache_write_tokens") or 0,
                "output_tokens": usage.get("output_tokens") or 0,
                "cost_usd": usage.get("cost_usd") or 0,
            }
        )
        .execute()
    )
    return first(res)


async def since(business_id: str, start: datetime, *, limit: int = 20000) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("contact_id,calls,input_tokens,cached_tokens,cache_write_tokens,output_tokens,cost_usd,created_at")
        .eq("business_id", business_id)
        .gte("created_at", start.isoformat())
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return rows(res)
