"""Supabase client singleton.

All database access in this project goes through the `db` package. Nothing
outside it may import this module's client directly — see plan.md §8.

The backend uses the service role key, which bypasses Row Level Security.
It must never reach the browser.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from supabase import AsyncClient, acreate_client

from config import settings

log = logging.getLogger(__name__)

_client: AsyncClient | None = None
_lock = asyncio.Lock()


async def get_db() -> AsyncClient:
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = await acreate_client(
                    settings.supabase_url,
                    settings.supabase_key,
                )
                log.info("supabase client created", extra={"url": settings.supabase_url})
    return _client


async def close_db() -> None:
    global _client
    _client = None


async def ping() -> dict[str, Any]:
    """Cheap connectivity check used by /health."""
    db = await get_db()
    res = await db.table("businesses").select("id").limit(1).execute()
    return {"ok": True, "rows": len(res.data or [])}


def rows(res: Any) -> list[dict[str, Any]]:
    return list(res.data or [])


def first(res: Any) -> dict[str, Any] | None:
    data = rows(res)
    return data[0] if data else None
