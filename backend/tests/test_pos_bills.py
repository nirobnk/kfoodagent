"""Recording a printed bill.

The POS is an invoice printer for WhatsApp orders, not a till. Two properties
have to hold for that to be safe:

  * A bill NEVER moves stock. Printing paper is not what takes a pack off the
    shelf — confirming the order in the dashboard is, and that already works.
  * A bill never dictates a price. The POS may have been offline for a week;
    the catalogue is what says what something costs.

The offline queue makes replay ordinary rather than exceptional, so idempotency
is tested here as a first-class behaviour, not an edge case.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import catalog
import db
import main
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

# REQUIRE_AUTH is false in conftest, so require_device yields the "DEV" device
# and bill numbers must carry that prefix.
BILL = "KF-DEV-20260919-001"


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


def bill(**overrides) -> dict:
    payload = {
        "bill_no": BILL,
        "printed_at": "2026-09-19T05:41:12+00:00",
        "customer": {"phone": "0771234567", "name": "Nimal", "address": "12 Galle Rd, Colombo"},
        "lines": [{"sku": "RAM-SHIN-5", "name": "Shin Ramyun Original — 5 Pack",
                   "variant": "5 Pack", "quantity": 2, "printed_unit_price": 3250}],
        "printed_totals": {"subtotal": 6500, "discount": 0, "tax": 0,
                           "delivery": 0, "total": 6500},
        "payment_method": "Bank Transfer",
    }
    payload.update(overrides)
    return payload


def tracked_single(fake, sku="RAM-SHIN-1", quantity=100):
    """Turn stock tracking on for one product, as staff would after a count."""
    for row in fake.tables["menu_items"]:
        if row["sku"] == sku:
            row["track_stock"] = True
            row["stock_quantity"] = quantity
            return row
    raise AssertionError(f"{sku} not seeded")


# --- the two guarantees ----------------------------------------------------

def test_printing_a_bill_never_moves_stock(client, wired):
    """The property the whole design rests on."""
    single = tracked_single(wired)
    before = single["stock_quantity"]

    res = client.post("/pos/bills", json=bill())
    assert res.status_code == 200

    assert single["stock_quantity"] == before
    assert wired.rows("inventory_movements") == []


def test_stock_moves_only_when_the_order_is_confirmed(client, wired):
    """A bill records the sale; confirming it is what sells the stock."""
    single = tracked_single(wired)
    created = client.post("/pos/bills", json=bill()).json()
    assert single["stock_quantity"] == 100

    order_id = created["order"]["id"]
    res = client.patch(f"/orders/{order_id}/status",
                       json={"status": "confirmed", "notify": False})
    assert res.status_code == 200
    # Two 5 Packs is ten singles off the shelf.
    assert single["stock_quantity"] == 90


def test_the_server_prices_the_bill_not_the_till(client, wired):
    """A tampered or stale unit price cannot move money."""
    res = client.post("/pos/bills", json=bill(
        lines=[{"sku": "RAM-SHIN-5", "quantity": 2, "printed_unit_price": 10}],
        printed_totals={"subtotal": 20, "discount": 0, "tax": 0, "delivery": 0, "total": 20},
    ))
    body = res.json()
    assert body["order"]["subtotal"] == 6500
    assert body["matches"] is False
    reasons = {d["reason"] for d in body["differences"]}
    assert "price_changed" in reasons


# --- idempotency, which the offline queue makes routine ---------------------

def test_replaying_a_bill_creates_nothing_new(client, wired):
    first = client.post("/pos/bills", json=bill()).json()
    second = client.post("/pos/bills", json=bill()).json()

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["order"]["id"] == first["order"]["id"]
    assert len(wired.rows("orders")) == 1
    assert len(wired.rows("order_invoices")) == 1


def test_a_replay_is_success_not_an_error(client, wired):
    client.post("/pos/bills", json=bill())
    res = client.post("/pos/bills", json=bill())
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_a_bill_number_from_another_device_is_refused(client, wired):
    res = client.post("/pos/bills", json=bill(bill_no="KF-MAC9-20260919-001"))
    assert res.status_code == 422


def test_a_malformed_bill_number_is_refused(client, wired):
    assert client.post("/pos/bills", json=bill(bill_no="bill-1")).status_code == 422


# --- custom lines ----------------------------------------------------------

def test_a_custom_line_carries_no_menu_item_id(client, wired):
    """That absence is exactly what makes it stock-neutral."""
    res = client.post("/pos/bills", json=bill(
        lines=[{"sku": None, "name": "Kimchi tub", "quantity": 1, "printed_unit_price": 900}],
        printed_totals={"subtotal": 900, "discount": 0, "tax": 0, "delivery": 400, "total": 1300},
    ))
    items = res.json()["order"]["items"]
    assert len(items) == 1
    assert "menu_item_id" not in items[0]
    assert items[0]["custom"] is True
    assert items[0]["unit_price"] == 900


def test_an_unknown_sku_is_demoted_not_rejected(client, wired):
    """The paper already exists; refusing would leave it with no row anywhere."""
    res = client.post("/pos/bills", json=bill(
        lines=[{"sku": "RAM-GONE-5", "name": "Discontinued", "quantity": 1,
                "printed_unit_price": 500}],
        printed_totals={"subtotal": 500, "discount": 0, "tax": 0, "delivery": 400, "total": 900},
    ))
    assert res.status_code == 200
    body = res.json()
    assert body["matches"] is False
    assert {d["reason"] for d in body["differences"]} >= {"sku_unknown"}
    assert body["order"]["items"][0]["custom"] is True


# --- money -----------------------------------------------------------------

def test_a_discount_cannot_exceed_the_subtotal(client, wired):
    res = client.post("/pos/bills", json=bill(
        printed_totals={"subtotal": 6500, "discount": 99999, "tax": 0,
                        "delivery": 0, "total": 0},
    ))
    assert res.json()["order"]["discount"] == 6500


def test_delivery_is_free_over_the_threshold(client, wired):
    """6500 is over the LKR 5,000 free-delivery threshold in the seeded profile."""
    res = client.post("/pos/bills", json=bill())
    assert res.json()["order"]["delivery_fee"] == 0


def test_delivery_is_charged_under_the_threshold(client, wired):
    res = client.post("/pos/bills", json=bill(
        lines=[{"sku": "RAM-SHIN-1", "quantity": 1, "printed_unit_price": 650}],
        printed_totals={"subtotal": 650, "discount": 0, "tax": 0, "delivery": 400, "total": 1050},
    ))
    order = res.json()["order"]
    assert order["delivery_fee"] == 400
    assert order["total"] == 1050


def test_a_delivery_override_is_honoured(client, wired):
    """A real courier quote for a remote address beats the flat rule."""
    res = client.post("/pos/bills", json=bill(delivery_override=1200))
    assert res.json()["order"]["delivery_fee"] == 1200


# --- the customer ----------------------------------------------------------

@pytest.mark.parametrize("phone", ["0771234567", "+94 77 123 4567", "94771234567",
                                   "077-123-4567", "0094771234567"])
def test_every_spelling_of_a_number_is_one_customer(client, wired, phone):
    client.post("/pos/bills", json=bill(customer={"phone": phone, "name": "Nimal"}))
    contacts = wired.rows("contacts")
    assert len(contacts) == 1
    assert contacts[0]["wa_id"] == "94771234567"


def test_a_number_that_is_not_a_phone_is_refused(client, wired):
    res = client.post("/pos/bills", json=bill(customer={"phone": "hello", "name": "X"}))
    assert res.status_code == 422
    # Nothing was written on the way to rejecting it.
    assert wired.rows("contacts") == []
    assert wired.rows("orders") == []


# --- an order the agent already made ---------------------------------------

def test_printing_for_an_existing_order_does_not_reprice_it(client, wired):
    """The agent already quoted this total to the customer on WhatsApp."""
    contact = wired.new_row("contacts", {"business_id": BUSINESS_ID, "wa_id": "94771234567",
                                         "name": "Nimal"})
    wired.seed("contacts", [contact])
    order = wired.new_row("orders", {
        "business_id": BUSINESS_ID, "contact_id": contact["id"],
        "items": [{"sku": "RAM-SHIN-5", "quantity": 2, "unit_price": 3000}],
        "subtotal": 6000, "total": 6000, "source": "agent",
    })
    wired.seed("orders", [order])

    res = client.post("/pos/bills", json=bill(order_id=order["id"]))
    assert res.status_code == 200
    assert len(wired.rows("orders")) == 1, "no second order was created"
    assert wired.rows("orders")[0]["total"] == 6000, "the agent's total stands"
    assert res.json()["invoice"]["order_id"] == order["id"]


def test_a_bill_for_another_customers_order_is_refused(client, wired):
    other = wired.new_row("contacts", {"business_id": BUSINESS_ID, "wa_id": "94770000000"})
    wired.seed("contacts", [other])
    order = wired.new_row("orders", {"business_id": BUSINESS_ID, "contact_id": other["id"],
                                     "items": [], "total": 100})
    wired.seed("orders", [order])

    res = client.post("/pos/bills", json=bill(order_id=order["id"]))
    assert res.status_code == 422


def test_a_bill_for_a_missing_order_is_refused(client, wired):
    res = client.post("/pos/bills", json=bill(order_id="11111111-0000-0000-0000-000000000000"))
    assert res.status_code == 404


# --- the mismatch record ---------------------------------------------------

def test_both_the_paper_and_the_catalogue_figures_are_kept(client, wired):
    """Paper is the contract with the customer; neither side overwrites the other."""
    client.post("/pos/bills", json=bill(
        lines=[{"sku": "RAM-SHIN-5", "quantity": 2, "printed_unit_price": 3000}],
        printed_totals={"subtotal": 6000, "discount": 0, "tax": 0, "delivery": 0, "total": 6000},
    ))
    invoice = wired.rows("order_invoices")[0]
    assert invoice["paper_total"] == 6000
    assert invoice["server_total"] == 6500
    assert invoice["mismatch"] is True
    assert invoice["mismatch_detail"]


def test_a_mismatch_is_written_where_staff_will_read_it(client, wired):
    client.post("/pos/bills", json=bill(
        lines=[{"sku": "RAM-SHIN-5", "quantity": 2, "printed_unit_price": 3000}],
        printed_totals={"subtotal": 6000, "discount": 0, "tax": 0, "delivery": 0, "total": 6000},
    ))
    notes = wired.rows("orders")[0]["notes"] or ""
    assert "Needs review" in notes
    assert BILL in notes


def test_a_matching_bill_raises_nothing(client, wired):
    res = client.post("/pos/bills", json=bill())
    assert res.json()["matches"] is True
    assert wired.rows("order_invoices")[0]["mismatch"] is False
    assert "Needs review" not in (wired.rows("orders")[0]["notes"] or "")


def test_the_order_records_where_it_came_from(client, wired):
    client.post("/pos/bills", json=bill())
    order = wired.rows("orders")[0]
    assert order["source"] == "pos"
    assert order["external_ref"] == BILL
    assert order["status"] == "new"
