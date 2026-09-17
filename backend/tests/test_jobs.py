"""Auto-return and rate limiting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import db
from jobs.auto_return import auto_return_once
from ratelimit import RateLimiter
from tests.conftest import BUSINESS_ID
from tests.fakes import FakeSupabase


@pytest.fixture
def fake_db(monkeypatch) -> FakeSupabase:
    fake = FakeSupabase()

    async def get_db():
        return fake

    monkeypatch.setattr(db.client, "get_db", get_db)
    monkeypatch.setattr(db.contacts, "get_db", get_db)
    return fake


def contact(minutes_ago: float | None, taken: bool = True) -> dict:
    started = (
        None
        if minutes_ago is None
        else (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    )
    return {
        "id": f"c{minutes_ago}",
        "business_id": BUSINESS_ID,
        "wa_id": "9477",
        "human_takeover": taken,
        "takeover_started_at": started,
        "takeover_by": "staff@kfood.lk",
    }


async def test_stale_takeovers_return_to_the_agent(fake_db):
    fake_db.seed("contacts", [contact(45), contact(10), contact(None, taken=False)])

    reverted = await auto_return_once(BUSINESS_ID)

    assert reverted == 1
    by_id = {c["id"]: c for c in fake_db.rows("contacts")}
    assert by_id["c45"]["human_takeover"] is False
    assert by_id["c45"]["takeover_started_at"] is None
    assert by_id["c10"]["human_takeover"] is True, "staff are still active on this chat"


async def test_nothing_to_do_is_not_an_error(fake_db):
    assert await auto_return_once(BUSINESS_ID) == 0


def test_rate_limiter_allows_then_blocks():
    limiter = RateLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        limiter.check("user-1")

    with pytest.raises(HTTPException) as exc:
        limiter.check("user-1")
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers

    limiter.check("user-2")  # a different user is unaffected


def test_rate_limiter_window_slides():
    limiter = RateLimiter(limit=1, window_seconds=0.01)
    limiter.check("user")
    import time

    time.sleep(0.02)
    limiter.check("user")
