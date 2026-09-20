"""Receipt evidence is separate from both chat messages and order payment state."""

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

    monkeypatch.setattr(db.payment_receipts, "get_db", get_db)
    return fake


async def test_receipt_is_idempotent_per_message(fake_db):
    values = {
        "business_id": BUSINESS_ID,
        "contact_id": "contact-1",
        "order_id": "order-1",
        "message_id": "message-1",
        "whatsapp_media_id": "media-1",
        "media_mime_type": "image/jpeg",
        "reported_detail": "payment done",
    }

    first = await db.payment_receipts.create(**values)
    second = await db.payment_receipts.create(**values)

    assert first["id"] == second["id"]
    assert len(fake_db.rows("payment_receipts")) == 1
    assert first["review_status"] == "pending_review"


async def test_analysis_fields_do_not_automatically_verify_receipt(fake_db):
    receipt = await db.payment_receipts.create(
        business_id=BUSINESS_ID,
        contact_id="contact-1",
        message_id="message-1",
    )

    updated = await db.payment_receipts.update_analysis(
        receipt["id"],
        extracted_data={"amount": "3650.00", "reference": "ABC123"},
        amount=3650,
        bank_name="HNB",
        transaction_reference="ABC123",
        confidence=0.93,
        review_status="details_match",
    )

    assert updated is not None
    assert updated["review_status"] == "details_match"
    assert updated["review_status"] != "verified"
    assert (await db.payment_receipts.list_for_order("order-1")) == []
