"""HTTP surface: the webhook Meta calls and the API the dashboard calls."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
import outbound
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, FakeWhatsApp

VERIFY_TOKEN = "verify-token-for-tests"
APP_SECRET = "app-secret"


@pytest.fixture
def client() -> TestClient:
    # No context manager: the lifespan (database ping, background job) stays off.
    return TestClient(main.app)


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


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def message_payload(text: str = "hello", wa_message_id: str = "wamid.1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "123456789"},
                            "contacts": [{"profile": {"name": "Nimal"}, "wa_id": "94771234567"}],
                            "messages": [
                                {
                                    "from": "94771234567",
                                    "id": wa_message_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# --- webhook verification -------------------------------------------------

def test_webhook_verification_returns_the_challenge_as_plain_text(client):
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 200
    assert response.text == "1158201444"
    assert response.headers["content-type"].startswith("text/plain")


def test_webhook_verification_rejects_a_wrong_token(client):
    response = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert response.status_code == 403


# --- webhook delivery -----------------------------------------------------

def test_webhook_rejects_an_unsigned_delivery(client, monkeypatch):
    body = json.dumps(message_payload()).encode()
    response = client.post("/webhook", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 403


def test_webhook_accepts_and_queues_a_signed_delivery(client, monkeypatch):
    processed = []

    async def capture(message, business_id=None):
        processed.append(message)

    monkeypatch.setattr(main, "process_inbound", capture)

    body = json.dumps(message_payload("what ramen do you have?")).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(body)},
    )

    assert response.status_code == 200
    assert response.json()["messages"] == 1
    # BackgroundTasks run once the response is returned.
    assert [m.text for m in processed] == ["what ramen do you have?"]


def test_webhook_ignores_a_payload_with_nothing_in_it(client):
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(body)},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_returns_200_even_for_junk(client):
    body = b"not json at all"
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(body)},
    )
    # Anything other than 200 makes Meta retry the same junk.
    assert response.status_code == 200


# --- staff API ------------------------------------------------------------

def seeded_contact(fake: FakeSupabase, hours_ago: float = 1.0) -> dict:
    contact = {
        "id": "22222222-2222-2222-2222-222222222222",
        "business_id": BUSINESS_ID,
        "wa_id": "94771234567",
        "name": "Nimal",
        "human_takeover": False,
        "unread_count": 3,
        "last_customer_message_at": (
            datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        ).isoformat(),
    }
    fake.seed("contacts", [contact])
    return contact


def test_staff_can_send_a_message_and_that_takes_over_the_chat(client, wired):
    fake, wa = wired
    contact = seeded_contact(fake)

    response = client.post(
        "/messages/send", json={"contact_id": contact["id"], "body": "On its way!"}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert wa.texts == [("94771234567", "On its way!")]
    assert fake.rows("contacts")[0]["human_takeover"] is True
    assert fake.rows("messages")[0]["sender"] == "human"


def test_staff_send_is_refused_outside_the_window(client, wired):
    fake, wa = wired
    contact = seeded_contact(fake, hours_ago=30)

    response = client.post("/messages/send", json={"contact_id": contact["id"], "body": "Hi"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "wa_message_id": None, "template_name": None,
                               "reason": "window_closed"}
    assert wa.texts == []


def test_unknown_contact_is_a_404(client, wired):
    response = client.post(
        "/messages/send",
        json={"contact_id": "33333333-3333-3333-3333-333333333333", "body": "Hi"},
    )
    assert response.status_code == 404


def test_takeover_toggle(client, wired):
    fake, _ = wired
    contact = seeded_contact(fake)

    on = client.post(f"/contacts/{contact['id']}/takeover", json={"enabled": True})
    assert on.status_code == 200
    assert fake.rows("contacts")[0]["human_takeover"] is True

    off = client.post(f"/contacts/{contact['id']}/takeover", json={"enabled": False})
    assert off.status_code == 200
    assert fake.rows("contacts")[0]["human_takeover"] is False
    assert fake.rows("contacts")[0]["takeover_started_at"] is None


def test_window_endpoint_reports_time_left(client, wired):
    fake, _ = wired
    contact = seeded_contact(fake, hours_ago=20)

    response = client.get(f"/contacts/{contact['id']}/window")

    body = response.json()
    assert body["open"] is True
    assert 3 * 3600 < body["remaining_seconds"] <= 4 * 3600
    assert body["remaining_human"].endswith("m")


def test_order_status_change_notifies_the_customer(client, wired):
    fake, wa = wired
    contact = seeded_contact(fake)
    fake.seed(
        "orders",
        [
            {
                "id": "44444444-4444-4444-4444-444444444444",
                "business_id": BUSINESS_ID,
                "contact_id": contact["id"],
                "order_number": 1043,
                "items": [{"name": "Shin Ramyun", "quantity": 2}],
                "total": 2400,
                "status": "new",
            }
        ],
    )

    response = client.patch(
        "/orders/44444444-4444-4444-4444-444444444444/status",
        json={"status": "confirmed"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["status"] == "confirmed"
    assert body["notified"] is True
    assert wa.texts == [("94771234567", "Order #1043 confirmed. Total Rs. 2,400.")]


def test_order_status_change_can_skip_the_notification(client, wired):
    fake, wa = wired
    contact = seeded_contact(fake)
    fake.seed(
        "orders",
        [{"id": "55555555-5555-5555-5555-555555555555", "business_id": BUSINESS_ID,
          "contact_id": contact["id"], "order_number": 1044, "items": [], "total": 100,
          "status": "new"}],
    )

    response = client.patch(
        "/orders/55555555-5555-5555-5555-555555555555/status",
        json={"status": "preparing", "notify": False},
    )

    assert response.json()["notified"] is False
    assert wa.texts == []


def test_unknown_order_is_a_404(client, wired):
    response = client.patch(
        "/orders/66666666-6666-6666-6666-666666666666/status", json={"status": "confirmed"}
    )
    assert response.status_code == 404


def test_invalid_status_is_rejected(client, wired):
    response = client.patch(
        "/orders/66666666-6666-6666-6666-666666666666/status", json={"status": "teleported"}
    )
    assert response.status_code == 422


def test_usage_counter(client, wired):
    fake, _ = wired
    fake.seed(
        "messages",
        [
            {"id": "1", "business_id": BUSINESS_ID, "direction": "out",
             "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "2", "business_id": BUSINESS_ID, "direction": "in",
             "created_at": datetime.now(timezone.utc).isoformat()},
        ],
    )

    body = client.get("/stats/usage").json()

    assert body["outbound_messages"] == 1
    assert body["inbound_messages"] == 1
    assert body["free_service_messages_remaining"] == 999


def test_staff_api_requires_a_token_when_auth_is_on(client, wired, monkeypatch):
    monkeypatch.setattr(main.settings, "require_auth", True)
    from config import settings as config_settings

    monkeypatch.setattr(config_settings, "require_auth", True)

    response = client.get("/contacts")

    assert response.status_code == 401


def test_health_reports_database_state(client, wired):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["whatsapp_configured"] is True
