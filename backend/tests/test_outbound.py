"""Outbound policy: the window is checked once, here, for every send."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import outbound
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, FakeWhatsApp
from whatsapp.client import WhatsAppError


@pytest.fixture
def wired(monkeypatch):
    fake = FakeSupabase()
    wa = FakeWhatsApp()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)
    monkeypatch.setattr(outbound, "get_client", lambda: wa)
    return fake, wa


def contact_row(hours_ago: float | None = 1.0) -> dict:
    last = (
        None
        if hours_ago is None
        else (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    )
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "wa_id": "94771234567",
        "name": "Nimal",
        "last_customer_message_at": last,
    }


async def test_text_sends_inside_the_window(wired):
    fake, wa = wired

    result = await outbound.send_text(
        business_id=BUSINESS_ID, contact=contact_row(1), body="Hello!"
    )

    assert result.ok is True
    assert wa.texts == [("94771234567", "Hello!")]
    saved = fake.rows("messages")[0]
    assert saved["direction"] == "out"
    assert saved["status"] == "sent"
    assert saved["wa_message_id"] == result.wa_message_id


async def test_text_is_refused_outside_the_window(wired):
    fake, wa = wired

    result = await outbound.send_text(
        business_id=BUSINESS_ID, contact=contact_row(30), body="Hello!"
    )

    assert result.ok is False
    assert result.reason == "window_closed"
    assert wa.texts == [], "no API call should be spent on a send Meta will reject"
    assert fake.rows("messages") == []


async def test_empty_body_is_not_sent(wired):
    _, wa = wired
    result = await outbound.send_text(business_id=BUSINESS_ID, contact=contact_row(), body="   ")
    assert result.ok is False and result.reason == "empty_body"
    assert wa.texts == []


async def test_failed_send_is_logged_as_failed(wired, monkeypatch):
    fake, _ = wired
    failing = FakeWhatsApp(fail_with=WhatsAppError("bad number", code=131026))
    monkeypatch.setattr(outbound, "get_client", lambda: failing)

    result = await outbound.send_text(
        business_id=BUSINESS_ID, contact=contact_row(), body="Hello!"
    )

    assert result.ok is False
    assert result.reason == "send_failed:131026"
    assert fake.rows("messages")[0]["status"] == "failed"


async def test_template_fallback_outside_the_window(wired):
    fake, wa = wired
    fake.seed(
        "templates",
        [
            {
                "id": "t1",
                "business_id": BUSINESS_ID,
                "key": "order_confirmed",
                "name": "order_confirmed",
                "language": "en",
                "variables": ["customer_name", "order_number", "total"],
                "body_preview": "Hello {{1}}, your K-Food order #{{2}} is confirmed. Total Rs. {{3}}.",
                "approved": True,
            }
        ],
    )

    result = await outbound.send_with_fallback(
        business_id=BUSINESS_ID,
        contact=contact_row(48),
        body="Order #1043 confirmed. Total Rs. 2,400.",
        template_key="order_confirmed",
        variables=["Nimal", 1043, "2,400"],
    )

    assert result.ok is True
    assert result.used_template is True
    assert wa.templates == [("94771234567", "order_confirmed", ["Nimal", 1043, "2,400"])]
    saved = fake.rows("messages")[0]
    assert saved["message_type"] == "template"
    assert saved["template_name"] == "order_confirmed"
    assert "Nimal" in saved["body"]


async def test_unapproved_template_is_not_sent(wired):
    fake, wa = wired
    fake.seed(
        "templates",
        [{"id": "t", "business_id": BUSINESS_ID, "key": "order_confirmed",
          "name": "order_confirmed", "language": "en", "variables": [], "approved": False}],
    )

    result = await outbound.send_template(
        business_id=BUSINESS_ID, contact=contact_row(48), key="order_confirmed"
    )

    assert result.ok is False and result.reason == "template_unavailable"
    assert wa.templates == []


async def test_template_variable_count_is_checked(wired):
    fake, wa = wired
    fake.seed(
        "templates",
        [{"id": "t", "business_id": BUSINESS_ID, "key": "order_confirmed",
          "name": "order_confirmed", "language": "en",
          "variables": ["a", "b", "c"], "approved": True}],
    )

    result = await outbound.send_template(
        business_id=BUSINESS_ID, contact=contact_row(), key="order_confirmed", variables=["only"]
    )

    assert result.ok is False and result.reason == "template_variable_mismatch"
    assert wa.templates == []


def test_order_status_messages_match_the_plan():
    order = {"order_number": 1043, "total": 2400}
    assert outbound.order_status_text("confirmed", order) == "Order #1043 confirmed. Total Rs. 2,400."
    assert outbound.order_status_text("preparing", order) == "We are preparing order #1043."
    assert outbound.order_status_text("dispatched", order) == "Order #1043 is on the way."
    assert outbound.order_status_text("delivered", order) == "Order #1043 delivered. Thank you!"
    assert outbound.order_status_text("new", order) is None


def test_order_template_variables_follow_the_approved_order():
    order = {"order_number": 1043, "total": 2400}
    contact = {"name": "Nimal"}
    assert outbound.order_template_variables("confirmed", order, contact) == ["Nimal", 1043, "2,400"]
    assert outbound.order_template_variables("dispatched", order, contact) == ["Nimal", 1043]
    assert outbound.order_template_variables("delivered", order, contact) == [1043]


async def test_order_notification_sends_free_text_inside_the_window(wired):
    _, wa = wired

    result = await outbound.notify_order_status(
        business_id=BUSINESS_ID,
        order={"order_number": 1043, "total": 2400},
        contact=contact_row(2),
        status="preparing",
    )

    assert result.ok is True
    assert wa.texts[0][1] == "We are preparing order #1043."


@pytest.mark.asyncio
async def test_an_image_goes_out_and_is_recorded(wired):
    fake, wa = wired

    result = await outbound.send_image(
        business_id=BUSINESS_ID,
        contact=contact_row(),
        image_url="https://kfoods.lk/binggrae-banana.jpeg",
        caption="Binggrae Banana Flavoured Milk",
    )

    assert result.ok
    assert wa.images == [
        ("94771234567", "https://kfoods.lk/binggrae-banana.jpeg", "Binggrae Banana Flavoured Milk")
    ]
    # The dashboard has to show staff that a photo went out, not a blank row.
    saved = fake.tables["messages"][-1]
    assert saved["body"] == "[photo] Binggrae Banana Flavoured Milk"
    assert saved["status"] == "sent"


@pytest.mark.asyncio
async def test_an_image_obeys_the_same_24_hour_window_as_text(wired):
    fake, wa = wired

    result = await outbound.send_image(
        business_id=BUSINESS_ID,
        contact=contact_row(hours_ago=30),
        image_url="https://kfoods.lk/binggrae-banana.jpeg",
    )

    assert result.ok is False
    assert result.reason == "window_closed"
    assert wa.images == []


@pytest.mark.asyncio
async def test_a_failed_image_is_recorded_as_failed(wired):
    fake, wa = wired
    wa.fail_with = WhatsAppError("bad media url", code=131053)

    result = await outbound.send_image(
        business_id=BUSINESS_ID,
        contact=contact_row(),
        image_url="https://kfoods.lk/missing.jpeg",
    )

    assert result.ok is False
    assert fake.tables["messages"][-1]["status"] == "failed"
