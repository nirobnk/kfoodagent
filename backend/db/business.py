"""The business row and its profile: delivery, payment, returns, contact.

Everything here comes from the kfoods.lk export and is seeded per business, so
nothing about K FOOD is hardcoded in the application.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .client import first, get_db

log = logging.getLogger(__name__)

TABLE = "businesses"
_CACHE_TTL = 300.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def get(business_id: str, *, refresh: bool = False) -> dict[str, Any]:
    """The business row, cached for five minutes — it changes almost never."""
    now = time.monotonic()
    cached = _cache.get(business_id)
    if cached and cached[0] > now and not refresh:
        return cached[1]

    db = await get_db()
    res = await db.table(TABLE).select("*").eq("id", business_id).limit(1).execute()
    business = first(res)
    if business is None:
        log.error("business row missing", extra={"business_id": business_id})
        return {}

    _cache[business_id] = (now + _CACHE_TTL, business)
    return business


async def get_profile(business_id: str) -> dict[str, Any]:
    return (await get(business_id)).get("profile") or {}


async def get_name(business_id: str) -> str:
    business = await get(business_id)
    profile = business.get("profile") or {}
    return profile.get("trading_name") or business.get("name") or "our shop"


def delivery_fee_for(profile: dict[str, Any], subtotal: float) -> float:
    """Flat island-wide courier fee, waived above the free-delivery threshold."""
    delivery = profile.get("delivery") or {}
    fee = float(delivery.get("fee") or 0)
    threshold = delivery.get("freeDeliveryThreshold")
    if threshold is not None and subtotal >= float(threshold):
        return 0.0
    return fee


def clear_cache() -> None:
    _cache.clear()
