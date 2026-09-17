"""Staff authentication for the dashboard API.

The dashboard signs in with Supabase Auth and sends that access token to this
backend. We verify the token, then check the user belongs to this business.
The WhatsApp token and the service role key never leave the backend.

Three verification paths, in order of preference:
  * SUPABASE_JWKS_URL set    -> asymmetric signatures (ES256/RS256) verified
                                locally against the project's published keys
  * SUPABASE_JWT_SECRET set  -> legacy HS256 secret, verified locally
  * otherwise                -> verified by Supabase /auth/v1/user, cached briefly
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

import db
from config import settings

log = logging.getLogger(__name__)

_CACHE_TTL = 60.0
_user_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_member_cache: dict[str, tuple[float, bool]] = {}


@dataclass(slots=True)
class Principal:
    user_id: str
    email: str | None
    business_id: str

    @property
    def label(self) -> str:
        return self.email or self.user_id


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    # Caches the signing keys and refreshes them when an unknown kid appears,
    # so key rotation needs no restart.
    return PyJWKClient(settings.supabase_jwks_url, cache_keys=True, lifespan=3600)


def _verify_jwks_sync(token: str) -> dict[str, Any] | None:
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "EdDSA"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
        return {"id": claims.get("sub"), "email": claims.get("email")}
    except jwt.PyJWTError as exc:
        log.info("token rejected by jwks", extra={"error": str(exc)})
        return None


async def _verify_jwks(token: str) -> dict[str, Any] | None:
    """PyJWKClient fetches over blocking urllib, so keep it off the event loop."""
    try:
        return await asyncio.to_thread(_verify_jwks_sync, token)
    except Exception as exc:
        log.error("jwks endpoint unreachable", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="auth backend unavailable"
        ) from exc


async def _verify_local(token: str) -> dict[str, Any] | None:
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
        return {"id": claims.get("sub"), "email": claims.get("email")}
    except jwt.PyJWTError as exc:
        log.info("token rejected locally", extra={"error": str(exc)})
        return None


async def _verify_remote(token: str) -> dict[str, Any] | None:
    url = f"{settings.supabase_url}/auth/v1/user"
    headers = {"Authorization": f"Bearer {token}", "apikey": settings.supabase_client_key}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        log.error("supabase auth unreachable", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="auth backend unavailable"
        ) from exc

    if response.status_code != 200:
        return None
    data = response.json()
    return {"id": data.get("id"), "email": data.get("email")}


async def _is_member(user_id: str, business_id: str) -> bool:
    key = f"{user_id}:{business_id}"
    cached = _member_cache.get(key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    client = await db.get_db()
    res = (
        await client.table("business_members")
        .select("user_id")
        .eq("business_id", business_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    allowed = bool(res.data)
    _member_cache[key] = (now + _CACHE_TTL, allowed)
    return allowed


async def require_staff(authorization: str | None = Header(default=None)) -> Principal:
    """FastAPI dependency: a signed-in staff member of this business."""
    if not settings.require_auth:
        return Principal(user_id="dev", email="dev@local", business_id=settings.business_id)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    key = _cache_key(token)
    now = time.monotonic()
    cached = _user_cache.get(key)
    if cached and cached[0] > now:
        user = cached[1]
    else:
        if settings.supabase_jwks_url:
            user = await _verify_jwks(token)
        elif settings.supabase_jwt_secret:
            user = await _verify_local(token)
        else:
            user = await _verify_remote(token)
        if not user or not user.get("id"):
            raise HTTPException(status_code=401, detail="invalid token")
        _user_cache[key] = (now + _CACHE_TTL, user)

    if not await _is_member(str(user["id"]), settings.business_id):
        log.warning("non-member token rejected", extra={"user_id": user.get("id")})
        raise HTTPException(status_code=403, detail="not a member of this business")

    return Principal(
        user_id=str(user["id"]), email=user.get("email"), business_id=settings.business_id
    )


StaffDep = Depends(require_staff)
