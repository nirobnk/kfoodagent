"""Unauthenticated routes, for kfoods.lk.

Everything here is already visible to anyone who opens the website. Nothing
about stock levels, customers, orders or the business's internals appears — see
`catalog.py` for why that is enforced with explicit models rather than trusted
to a database projection.

These are the only routes in the application with HTTP caching, because they are
the only ones a CDN should ever hold. Both carry an ETag, so a repeat visitor
and a site build both revalidate in a few bytes instead of refetching 90 products.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request, Response

import catalog
import schemas
from config import settings

log = logging.getLogger(__name__)

public = APIRouter(prefix="/public", tags=["public"])

# The catalogue changes a few times a month, so it may be held for minutes and
# served stale for a day while a revalidation happens behind the scenes.
CATALOG_CACHE = "public, max-age=300, stale-while-revalidate=86400"
# Availability changes whenever an order is confirmed. Short, deliberately.
AVAILABILITY_CACHE = "public, max-age=60"


def _not_modified(if_none_match: str | None, version: str) -> bool:
    if not if_none_match:
        return False
    # A caching proxy may weaken the tag or send a list; match on substring
    # rather than demanding an exact string it never promised to preserve.
    return version in if_none_match


@public.get("/catalog", response_model=schemas.PublicCatalogResponse)
async def public_catalog(
    response: Response,
    request: Request,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """The product catalogue the website builds itself from."""
    payload, version = await catalog.public_catalog(settings.business_id)

    if _not_modified(if_none_match, version):
        # 304 must carry the validators and no body.
        return Response(
            status_code=304,
            headers={"ETag": f'"{version}"', "Cache-Control": CATALOG_CACHE},
        )

    response.headers["ETag"] = f'"{version}"'
    response.headers["Cache-Control"] = CATALOG_CACHE
    return payload


@public.get("/availability", response_model=schemas.AvailabilityResponse)
async def public_availability(
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """Whether each SKU can be sold. In stock or out, never a count.

    Until staff turn `track_stock` on for a product, every SKU reports
    `in_stock` — which is exactly how the site behaves today, so nothing changes
    on the day this ships.
    """
    payload, version = await catalog.availability(settings.business_id)

    if _not_modified(if_none_match, version):
        return Response(
            status_code=304,
            headers={"ETag": f'"{version}"', "Cache-Control": AVAILABILITY_CACHE},
        )

    response.headers["ETag"] = f'"{version}"'
    response.headers["Cache-Control"] = AVAILABILITY_CACHE
    return payload
