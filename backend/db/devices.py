"""Device tokens: the credential a shop Mac uses to reach the API.

A device is a principal that is a machine. It has no Supabase Auth identity and
no business_members row, and it reaches only the /pos routes — so a token sitting
in localStorage on a shared counter Mac cannot message a customer.

Only the sha256 of a token is ever stored. Nothing in this module can return a
usable credential; minting happens once, in scripts/mint_device_token.py.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "device_tokens"

# Prefixed so a leaked string is recognisable in a log or a paste, the way
# GitHub's ghp_ tokens are.
TOKEN_PREFIX = "kfpos_"
PREFIX_STORED = 14  # characters of the raw token kept in clear, for naming it

# Everything except the hash. Used wherever a token is described rather than
# verified, so the hash cannot leak into a response by accident.
SAFE_FIELDS = (
    "id,business_id,device_id,name,token_prefix,scopes,"
    "revoked_at,revoked_by,last_seen_at,created_by,created_at"
)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> tuple[str, str, str]:
    """A new credential: (raw, prefix, hash). The raw is shown once, then lost."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:PREFIX_STORED], hash_token(raw)


def is_live(device: dict[str, Any] | None) -> bool:
    """Revocation is checked here, in Python, not in the query.

    PostgREST could filter `revoked_at is null`, but the test fake has no `is_`
    operator, so a query-side check would be untestable — and a revocation test
    that cannot run is worse than an extra line.
    """
    return bool(device) and device.get("revoked_at") is None


async def get_by_hash(token_hash: str) -> dict[str, Any] | None:
    """Look up a token by its hash. Returns revoked rows too; callers check."""
    db = await get_db()
    res = await db.table(TABLE).select("*").eq("token_hash", token_hash).limit(1).execute()
    return first(res)


async def list_for_business(business_id: str) -> list[dict[str, Any]]:
    """Every device, live or revoked. Never includes the hash."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select(SAFE_FIELDS)
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .execute()
    )
    # select() projection is not honoured by the test fake, so strip explicitly.
    # Relying on the projection alone would pass in tests and leak in production.
    return [_safe(row) for row in rows(res)]


async def create(
    *,
    business_id: str,
    device_id: str,
    name: str,
    created_by: str = "owner",
) -> tuple[dict[str, Any], str]:
    """Mint a device token. Returns (row, raw_token); the raw is never stored."""
    raw, prefix, token_hash = generate_token()
    db = await get_db()
    res = (
        await db.table(TABLE)
        .insert(
            {
                "business_id": business_id,
                "device_id": device_id.strip().upper(),
                "name": name.strip(),
                "token_prefix": prefix,
                "token_hash": token_hash,
                "created_by": created_by,
            }
        )
        .execute()
    )
    created = first(res)
    if created is None:
        raise RuntimeError("device token insert returned no row")
    log.info(
        "device token minted",
        extra={"device_id": created.get("device_id"), "created_by": created_by},
    )
    return _safe(created), raw


async def revoke(business_id: str, token_id: str, *, revoked_by: str) -> dict[str, Any] | None:
    """One row is all it takes to make a lost Mac useless."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .update(
            {
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "revoked_by": revoked_by,
            }
        )
        .eq("business_id", business_id)
        .eq("id", token_id)
        .execute()
    )
    device = first(res)
    if device:
        log.warning(
            "device token revoked",
            extra={"device_id": device.get("device_id"), "revoked_by": revoked_by},
        )
    return _safe(device) if device else None


async def touch(token_id: str) -> None:
    """Record that a device is alive. Never raises — a bill must not wait on it."""
    try:
        db = await get_db()
        await (
            db.table(TABLE)
            .update({"last_seen_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", token_id)
            .execute()
        )
    except Exception:
        log.debug("could not touch device last_seen_at", exc_info=True)


def _safe(row: dict[str, Any] | None) -> dict[str, Any]:
    """Strip the hash. The only way a token row leaves this module."""
    if not row:
        return {}
    return {key: value for key, value in row.items() if key != "token_hash"}
