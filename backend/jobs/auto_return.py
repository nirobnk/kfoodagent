"""Background job: give the chat back to the agent when staff go quiet.

Staff forget to switch back. Without this the customer gets silence.
"""

from __future__ import annotations

import asyncio
import logging

import db
from config import settings

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 300  # every 5 minutes


async def auto_return_once(business_id: str | None = None) -> int:
    business_id = business_id or settings.business_id
    reverted = await db.contacts.expire_takeovers(business_id, settings.auto_return_minutes)
    return len(reverted)


async def auto_return_loop(stop: asyncio.Event) -> None:
    log.info(
        "auto-return job started",
        extra={"interval_s": INTERVAL_SECONDS, "after_minutes": settings.auto_return_minutes},
    )
    while not stop.is_set():
        try:
            count = await auto_return_once()
            if count:
                log.info("auto-return handed chats back to the agent", extra={"count": count})
        except Exception:
            log.exception("auto-return job iteration failed")

        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_SECONDS)
        except TimeoutError:
            continue
    log.info("auto-return job stopped")
