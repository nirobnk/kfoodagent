"""Click-to-WhatsApp ad taps: which ad started which chat."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "ad_referrals"


async def record(
    *,
    business_id: str,
    contact_id: str,
    message_id: str | None,
    referral: dict[str, Any],
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "contact_id": contact_id,
                "message_id": message_id,
                "source_type": referral.get("source_type"),
                "source_id": referral.get("source_id"),
                "source_url": referral.get("source_url"),
                "headline": referral.get("headline"),
                "body": referral.get("body"),
                "media_type": referral.get("media_type"),
                "media_url": referral.get("media_url"),
                "ctwa_clid": referral.get("ctwa_clid"),
                "raw": referral.get("raw") or {},
            }
        )
        .execute()
    )
    return first(res)


async def since(business_id: str, start: datetime, *, limit: int = 5000) -> list[dict[str, Any]]:
    """Every ad tap from `start` on, oldest first."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id,contact_id,source_type,source_id,source_url,headline,media_type,created_at")
        .eq("business_id", business_id)
        .gte("created_at", start.isoformat())
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return rows(res)
