"""The catalogue, shaped for the website and the POS.

One place builds these payloads, so the shop's prices cannot differ between
what a customer reads on kfoods.lk and what staff print on an invoice. That was
the whole reason for connecting these surfaces to the backend.

Two audiences, two shapes, and the difference matters:

  * `public_catalog()` is served unauthenticated. It carries no stock, ever.
    An exact count tells a competitor the shop's sales volume, and a boolean
    tells a customer everything they actually need.
  * `pos_catalog()` sits behind a device token and does carry stock, because
    staff pricing a parcel should see what is on the shelf.

Both are built from EXPLICIT pydantic models rather than by handing database
rows to FastAPI. `menu_items` carries `stock_quantity` on every row, so a dict
passthrough would publish it. PostgREST column projection is not a defence
either: the test fake ignores projection, so that leak would pass every test.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import db
import schemas

log = logging.getLogger(__name__)

# The catalogue changes a few times a month. Rebuilding it per request would be
# 90 rows of pointless work; this is short enough that a price edit shows up
# while someone is still looking at the screen.
_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, Any, str]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version(payload: Any) -> str:
    """An ETag derived from the bytes themselves.

    `menu_items` has no `updated_at`, so there is no cheaper honest signal — and
    a hash of the body can never claim freshness the body does not have.
    """
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def availability_of(product: dict[str, Any], variant: dict[str, Any]) -> str:
    """Whether this pack can be made from the singles on the shelf.

    Stock is counted in single units on the product's `units = 1` row, so a
    5 Pack needs five of them and a carton needs twenty. An untracked product is
    unlimited, exactly as every product behaved before stock existed.

    Note that in production every product IS tracked — all 30 were switched on
    with a placeholder of 1000 singles — so this is live, not dormant. Nothing
    reports out_of_stock today only because those numbers are high.
    """
    if not product.get("track_stock"):
        return "in_stock"
    on_hand = int(product.get("stock_quantity") or 0)
    per_pack = max(1, int(variant.get("units") or 1))
    return "in_stock" if on_hand >= per_pack else "out_of_stock"


def _store(profile: dict[str, Any], products: list[dict[str, Any]]) -> schemas.PublicStore:
    """The facts the website currently hardcodes into its own markup."""
    delivery = profile.get("delivery") or {}
    payment = profile.get("payment") or {}
    contact = profile.get("contact") or {}

    prices = [
        float(v.get("price") or 0)
        for p in products
        for v in p.get("variants", [])
        if v.get("price")
    ]
    price_range = None
    if prices:
        price_range = f"LKR {min(prices):,.0f} – LKR {max(prices):,.0f}"

    threshold = delivery.get("freeDeliveryThreshold")
    return schemas.PublicStore(
        name=profile.get("trading_name") or profile.get("name") or "K FOOD",
        site=profile.get("website"),
        currency="LKR",
        whatsapp=(contact.get("whatsapp") or {}).get("number")
        or (contact.get("whatsapp") or {}).get("displayNumber"),
        delivery_fee=float(delivery.get("fee") or 0),
        free_delivery_threshold=float(threshold) if threshold is not None else None,
        price_range=price_range,
        bank=payment.get("bankDetails") or {},
        returns=profile.get("returns") or {},
    )


async def _grouped(business_id: str) -> list[dict[str, Any]]:
    variants = await db.menu.list_available(business_id)
    return db.menu.group_by_product(variants)


def _base_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": product.get("handle") or "",
        "name": product.get("product_name") or "",
        "ko": product.get("korean_name"),
        "brand": product.get("brand"),
        "category": product.get("category"),
        "pack": product.get("pack_size"),
        "heat": product.get("heat_level"),
        "cook": product.get("cook_time"),
        "badge": product.get("badge"),
        "short": product.get("description"),
        "image_url": product.get("image_url"),
        "product_url": product.get("product_url"),
    }


async def public_catalog(business_id: str) -> tuple[schemas.PublicCatalogResponse, str]:
    """The catalogue as kfoods.lk sees it. No stock, no customers."""
    cached = _cache.get("public")
    if cached and cached[0] > time.monotonic():
        return cached[1], cached[2]

    grouped = await _grouped(business_id)
    profile = await db.business.get_profile(business_id)

    products = [
        schemas.PublicProduct(
            **_base_product(product),
            variants=[
                schemas.PublicVariant(
                    sku=str(v.get("sku") or ""),
                    label=v.get("label"),
                    price=float(v.get("price") or 0),
                    units=int(v.get("units") or 1),
                )
                for v in product.get("variants", [])
            ],
        )
        for product in grouped
    ]

    payload = schemas.PublicCatalogResponse(
        generated_at=_now_iso(),
        version="",
        store=_store(profile, grouped),
        categories=_categories(grouped),
        products=products,
    )
    # The timestamp must not feed the hash, or every request would look changed.
    version = _version(payload.model_dump(exclude={"generated_at", "version"}))
    payload.version = version

    _cache["public"] = (time.monotonic() + _CACHE_TTL, payload, version)
    return payload, version


async def pos_catalog(business_id: str) -> tuple[schemas.PosCatalogResponse, str]:
    """The catalogue as the till sees it: the same prices, plus stock."""
    grouped = await _grouped(business_id)
    profile = await db.business.get_profile(business_id)

    products = [
        schemas.PosProduct(
            **_base_product(product),
            track_stock=bool(product.get("track_stock")),
            stock_quantity=int(product.get("stock_quantity") or 0),
            variants=[
                schemas.PosVariant(
                    sku=str(v.get("sku") or ""),
                    label=v.get("label"),
                    price=float(v.get("price") or 0),
                    units=int(v.get("units") or 1),
                    track_stock=bool(product.get("track_stock")),
                    stock_quantity=int(product.get("stock_quantity") or 0),
                )
                for v in product.get("variants", [])
            ],
        )
        for product in grouped
    ]

    payload = schemas.PosCatalogResponse(
        generated_at=_now_iso(),
        version="",
        store=_store(profile, grouped),
        categories=_categories(grouped),
        products=products,
    )
    payload.version = _version(payload.model_dump(exclude={"generated_at", "version"}))
    return payload, payload.version


async def availability(business_id: str) -> tuple[schemas.AvailabilityResponse, str]:
    """One state per SKU. Two values only, and never a number."""
    grouped = await _grouped(business_id)
    items = [
        schemas.AvailabilityItem(
            handle=str(product.get("handle") or ""),
            sku=str(variant.get("sku") or ""),
            state=availability_of(product, variant),
        )
        for product in grouped
        for variant in product.get("variants", [])
    ]
    payload = schemas.AvailabilityResponse(generated_at=_now_iso(), items=items)
    version = _version([i.model_dump() for i in items])
    return payload, version


def _categories(grouped: list[dict[str, Any]]) -> list[str]:
    """Distinct categories in catalogue order, not alphabetical."""
    seen: list[str] = []
    for product in grouped:
        category = product.get("category")
        if category and category not in seen:
            seen.append(str(category))
    return seen


def clear_cache() -> None:
    """Tests, and anything that changes a price and wants it visible at once."""
    _cache.clear()
