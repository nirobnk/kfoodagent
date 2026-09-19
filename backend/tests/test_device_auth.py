"""The boundary between a person and a machine.

The POS holds a credential on a shop Mac several people use. The guarantee this
file exists to prove is that the credential reaches the catalogue and the order
routes and nothing else — in particular it can never message a customer.

That guarantee is structural, not a matter of remembering to check: staff auth
reads `Authorization`, device auth reads `X-Device-Token`, and neither header
can satisfy the other dependency. Two tests below assert exactly that, in both
directions.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
import main
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

RAW_TOKEN = "kfpos_test_token_for_the_shop_mac"


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


@pytest.fixture
def wired(monkeypatch):
    """A seeded database with one live device, and real auth switched on."""
    fake = FakeSupabase()
    seed_kfood(fake, BUSINESS_ID)

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)

    fake.seed(
        "device_tokens",
        [
            {
                "id": "device-1",
                "business_id": BUSINESS_ID,
                "device_id": "MAC1",
                "name": "Shop Mac",
                "token_prefix": RAW_TOKEN[:14],
                "token_hash": db.devices.hash_token(RAW_TOKEN),
                "scopes": ["catalog", "orders"],
                "revoked_at": None,
            }
        ],
    )

    # conftest sets REQUIRE_AUTH=false so every other test can skip tokens.
    # These tests are about verification, so it has to be back on.
    monkeypatch.setattr(config.settings, "require_auth", True)
    monkeypatch.setattr(main.settings, "require_auth", True, raising=False)
    auth._device_cache.clear()
    auth._device_seen.clear()
    return fake


def test_a_live_token_reaches_the_catalogue(client, wired):
    res = client.get("/pos/catalog", headers={"X-Device-Token": RAW_TOKEN})
    assert res.status_code == 200
    assert len(res.json()["products"]) == 3


def test_an_unknown_token_is_refused(client, wired):
    res = client.get("/pos/catalog", headers={"X-Device-Token": "kfpos_not_a_real_token"})
    assert res.status_code == 401


def test_a_revoked_token_is_refused(client, wired):
    wired.tables["device_tokens"][0]["revoked_at"] = "2026-09-19T00:00:00+00:00"
    auth._device_cache.clear()
    res = client.get("/pos/catalog", headers={"X-Device-Token": RAW_TOKEN})
    assert res.status_code == 401


def test_a_revoked_token_is_indistinguishable_from_an_unknown_one(client, wired):
    """Saying which one it is tells a caller whether they guessed a real token."""
    wired.tables["device_tokens"][0]["revoked_at"] = "2026-09-19T00:00:00+00:00"
    auth._device_cache.clear()
    revoked = client.get("/pos/catalog", headers={"X-Device-Token": RAW_TOKEN})
    unknown = client.get("/pos/catalog", headers={"X-Device-Token": "kfpos_nope"})
    assert revoked.status_code == unknown.status_code == 401
    assert revoked.json()["detail"] == unknown.json()["detail"]


def test_no_token_at_all_is_refused(client, wired):
    assert client.get("/pos/catalog").status_code == 401


# --- the two that matter ---------------------------------------------------

def test_a_device_token_cannot_send_a_whatsapp_message(client, wired):
    """The whole reason the POS does not simply use a staff login."""
    res = client.post(
        "/messages/send",
        headers={"X-Device-Token": RAW_TOKEN},
        json={"contact_id": "whatever", "body": "hello"},
    )
    assert res.status_code == 401


def test_a_device_token_cannot_reach_any_staff_route(client, wired):
    """Sweep the staff surface rather than trusting one example of it."""
    headers = {"X-Device-Token": RAW_TOKEN}
    assert client.get("/inventory", headers=headers).status_code == 401
    assert client.get("/orders", headers=headers).status_code == 401
    assert client.get("/contacts", headers=headers).status_code == 401
    assert client.get("/devices", headers=headers).status_code == 401
    assert client.post(
        "/contacts/x/takeover", headers=headers, json={"enabled": True}
    ).status_code == 401
    assert client.patch(
        "/orders/x/status", headers=headers, json={"status": "confirmed"}
    ).status_code == 401


def test_a_staff_bearer_token_cannot_reach_the_pos_routes(client, wired):
    """The boundary holds in the other direction too."""
    res = client.get("/pos/catalog", headers={"Authorization": "Bearer a.staff.jwt"})
    assert res.status_code == 401


def test_the_token_hash_is_never_returned(client, wired):
    devices = db.devices
    rows = wired.tables["device_tokens"]
    assert "token_hash" in rows[0], "the fixture should store a hash"
    safe = devices._safe(rows[0])
    assert "token_hash" not in safe
    assert safe["token_prefix"] == RAW_TOKEN[:14]
