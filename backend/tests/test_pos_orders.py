"""The order list the POS prints from.

The trap this file guards: `db.orders.list_for_business` fetches the customer
with PostgREST FK embedding (`select("*, contacts(...)")`), which `FakeQuery`
ignores entirely. A test written against that would pass on a payload with no
customer on it, and the shop would print a nameless invoice. `list_for_pos`
therefore uses two plain queries, and these tests assert the customer is really
there.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import catalog
import db
import main
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


@pytest.fixture
def wired(monkeypatch):
    fake = FakeSupabase()
    seed_kfood(fake, BUSINESS_ID)

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)
    db.business.clear_cache()
    catalog.clear_cache()
    return fake


def an_order(fake, *, wa_id="94771234567", name="Nimal", status="new", total=6500):
    contact = fake.new_row("contacts", {"business_id": BUSINESS_ID, "wa_id": wa_id, "name": name})
    fake.seed("contacts", [contact])
    order = fake.new_row("orders", {
        "business_id": BUSINESS_ID, "contact_id": contact["id"],
        "items": [{"sku": "RAM-SHIN-5", "name": "Shin Ramyun Original — 5 Pack",
                   "quantity": 2, "unit_price": 3250}],
        "subtotal": total, "total": total, "status": status, "source": "agent",
    })
    fake.seed("orders", [order])
    return contact, order


def test_an_order_carries_its_customer(client, wired):
    """The name and number that go on the invoice."""
    an_order(wired)
    orders = client.get("/pos/orders").json()["orders"]
    assert len(orders) == 1
    customer = orders[0]["customer"]
    assert customer is not None, "FK embedding would have silently returned None here"
    assert customer["name"] == "Nimal"
    assert customer["wa_id"] == "94771234567"


def test_the_invoice_shows_a_number_a_customer_recognises(client, wired):
    an_order(wired)
    customer = client.get("/pos/orders").json()["orders"][0]["customer"]
    assert customer["display_phone"] == "0771234567"


def test_several_orders_each_get_their_own_customer(client, wired):
    an_order(wired, wa_id="94771234567", name="Nimal")
    an_order(wired, wa_id="94770000001", name="Kamala")
    orders = client.get("/pos/orders").json()["orders"]
    names = {o["customer"]["name"] for o in orders}
    assert names == {"Nimal", "Kamala"}


def test_finished_orders_are_not_offered_for_printing(client, wired):
    an_order(wired, status="delivered", wa_id="94770000002")
    an_order(wired, status="cancelled", wa_id="94770000003")
    an_order(wired, status="new", wa_id="94771234567")
    orders = client.get("/pos/orders").json()["orders"]
    assert [o["status"] for o in orders] == ["new"]


def test_one_order_can_be_fetched_with_its_invoices(client, wired):
    _, order = an_order(wired)
    body = client.get(f"/pos/orders/{order['id']}").json()
    assert body["id"] == order["id"]
    assert body["customer"]["name"] == "Nimal"
    assert body["invoices"] == []


def test_a_printed_order_lists_its_bill(client, wired):
    _, order = an_order(wired)
    client.post("/pos/bills", json={
        "bill_no": "KF-DEV-20260919-007",
        "printed_at": "2026-09-19T05:41:12+00:00",
        "order_id": order["id"],
        "customer": {"phone": "0771234567", "name": "Nimal"},
        "lines": [{"sku": "RAM-SHIN-5", "quantity": 2, "printed_unit_price": 3250}],
        "printed_totals": {"subtotal": 6500, "discount": 0, "tax": 0,
                           "delivery": 0, "total": 6500},
    })
    body = client.get(f"/pos/orders/{order['id']}").json()
    assert [i["bill_no"] for i in body["invoices"]] == ["KF-DEV-20260919-007"]


def test_a_missing_order_is_a_404(client, wired):
    assert client.get("/pos/orders/11111111-0000-0000-0000-000000000000").status_code == 404


# --- looking a customer up before printing ---------------------------------

def test_a_known_customer_is_found_with_their_open_order(client, wired):
    an_order(wired)
    body = client.get("/pos/contacts/lookup", params={"phone": "077 123 4567"}).json()
    assert body["found"] is True
    assert body["contact"]["name"] == "Nimal"
    assert body["open_order"]["total"] == 6500


def test_an_unknown_customer_is_not_an_error(client, wired):
    res = client.get("/pos/contacts/lookup", params={"phone": "0770000009"})
    assert res.status_code == 200
    assert res.json()["found"] is False


def test_looking_someone_up_never_creates_them(client, wired):
    """Otherwise the dashboard inbox fills with chats that never happened."""
    client.get("/pos/contacts/lookup", params={"phone": "0770000009"})
    assert wired.rows("contacts") == []


def test_a_nonsense_number_is_refused(client, wired):
    assert client.get("/pos/contacts/lookup", params={"phone": "abc"}).status_code == 422
