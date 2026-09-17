"""Meta retries webhook deliveries. The message log must not grow duplicates."""

from __future__ import annotations

import pytest

import db
from tests.conftest import BUSINESS_ID
from tests.fakes import FakeSupabase


@pytest.fixture
def fake_db(monkeypatch) -> FakeSupabase:
    fake = FakeSupabase()

    async def get_db():
        return fake

    monkeypatch.setattr(db.client, "get_db", get_db)
    monkeypatch.setattr(db.messages, "get_db", get_db)
    monkeypatch.setattr(db.contacts, "get_db", get_db)
    return fake


CONTACT_ID = "22222222-2222-2222-2222-222222222222"


async def save_inbound(wa_message_id: str) -> dict | None:
    return await db.messages.save(
        business_id=BUSINESS_ID,
        contact_id=CONTACT_ID,
        direction="in",
        sender="customer",
        body="hello",
        wa_message_id=wa_message_id,
    )


async def test_same_wa_message_id_is_stored_once(fake_db):
    first = await save_inbound("wamid.ABC")
    second = await save_inbound("wamid.ABC")

    assert first is not None
    assert second is None, "a repeated delivery must not create a second row"
    assert len(fake_db.rows("messages")) == 1


async def test_different_ids_are_both_stored(fake_db):
    await save_inbound("wamid.A")
    await save_inbound("wamid.B")

    assert len(fake_db.rows("messages")) == 2


async def test_outbound_without_wa_id_always_inserts(fake_db):
    for _ in range(2):
        await db.messages.save(
            business_id=BUSINESS_ID,
            contact_id=CONTACT_ID,
            direction="out",
            sender="agent",
            body="hi",
        )

    assert len(fake_db.rows("messages")) == 2


async def test_exists_reports_stored_messages(fake_db):
    assert await db.messages.exists("wamid.X") is False
    await save_inbound("wamid.X")
    assert await db.messages.exists("wamid.X") is True


async def test_status_never_goes_backwards(fake_db):
    await save_inbound("wamid.S")

    await db.messages.update_status("wamid.S", "read")
    await db.messages.update_status("wamid.S", "delivered")

    assert fake_db.rows("messages")[0]["status"] == "read"


async def test_failure_status_always_applies(fake_db):
    await save_inbound("wamid.F")

    await db.messages.update_status("wamid.F", "read")
    await db.messages.update_status("wamid.F", "failed", error="Re-engagement message")

    row = fake_db.rows("messages")[0]
    assert row["status"] == "failed"
    assert row["error"] == "Re-engagement message"


async def test_contact_get_or_create_is_stable(fake_db):
    first = await db.contacts.get_or_create(BUSINESS_ID, "94771234567", name="Nimal")
    second = await db.contacts.get_or_create(BUSINESS_ID, "94771234567")

    assert first["id"] == second["id"]
    assert len(fake_db.rows("contacts")) == 1
