"""The CRM: what the orders say about a customer, and what staff do about it.

Two halves. The first exercises `crm.py`, which is pure arithmetic over a list
of orders — that is where every segment rule actually lives, so it is where the
rules are pinned down. The second drives the HTTP surface the dashboard calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import auth
import config
import crm
import db
import main
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase

CONTACT_ID = "22222222-2222-2222-2222-222222222222"
OTHER_ID = "33333333-3333-3333-3333-333333333333"
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def order(
    *,
    days_ago: int,
    total: float,
    status: str = "delivered",
    items: list[dict] | None = None,
    contact_id: str = CONTACT_ID,
    source: str = "agent",
) -> dict:
    return {
        "id": f"order-{days_ago}-{total}-{contact_id[:4]}",
        "business_id": BUSINESS_ID,
        "contact_id": contact_id,
        "status": status,
        "total": total,
        "subtotal": total,
        "source": source,
        "items": items if items is not None else [{"name": "Shin Ramyun — 5 Pack", "quantity": 1}],
        "created_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


# ---------------------------------------------------------------------------
# crm.py — the arithmetic
# ---------------------------------------------------------------------------
def test_a_contact_who_never_ordered_is_a_lead_with_nothing_to_score():
    stats = crm.summarise([], now=NOW)

    assert stats.orders == 0
    assert stats.lifetime_value == 0
    assert stats.recency_score == stats.frequency_score == stats.monetary_score == 0
    assert stats.suggested_lifecycle == "lead"
    assert stats.days_since_last_order is None


def test_a_cancelled_order_is_counted_but_not_charged_for():
    """It has to appear somewhere — staff need to see a customer who cancels."""
    stats = crm.summarise(
        [order(days_ago=2, total=1200), order(days_ago=1, total=9000, status="cancelled")],
        now=NOW,
    )

    assert stats.orders == 1
    assert stats.cancelled_orders == 1
    assert stats.lifetime_value == 1200
    assert stats.average_order == 1200


def test_lifetime_value_survives_numerics_arriving_as_strings():
    """PostgREST hands back numeric(10,2) as a string. float() on it, not sum()."""
    stats = crm.summarise([order(days_ago=1, total="1450.50")], now=NOW)  # type: ignore[arg-type]

    assert stats.lifetime_value == 1450.50


def test_favourites_rank_by_quantity_across_orders():
    orders = [
        order(days_ago=3, total=2000, items=[
            {"name": "Buldak 2x Spicy", "quantity": 2, "sku": "RAM-BUL-2X-1"},
            {"name": "Shin Ramyun Black", "quantity": 1},
        ]),
        order(days_ago=10, total=1800, items=[{"name": "Buldak 2x Spicy", "quantity": 3}]),
    ]

    favourites = crm.summarise(orders, now=NOW).favourites

    assert favourites[0].name == "Buldak 2x Spicy"
    assert favourites[0].quantity == 5
    assert favourites[0].orders == 2, "appeared on two separate orders"
    assert favourites[0].sku == "RAM-BUL-2X-1"


def test_a_frequent_recent_big_spender_is_a_vip():
    orders = [order(days_ago=day, total=4500) for day in (1, 5, 9, 14, 21, 28, 40)]

    stats = crm.summarise(orders, now=NOW)

    assert stats.frequency_score >= 4
    assert stats.monetary_score >= 4
    assert stats.suggested_lifecycle == "vip"


def test_a_regular_who_has_gone_quiet_is_at_risk_not_a_vip():
    """The rule that earns this module its keep: silence outranks money.

    Six orders about a fortnight apart, then six weeks of nothing. The bands
    alone would call this a VIP — the spend and the count both clear — and a
    CRM that shows them as fine is a CRM where nobody sends the message.
    """
    orders = [order(days_ago=day, total=6000) for day in (45, 52, 60, 75, 90, 110)]

    stats = crm.summarise(orders, now=NOW)

    assert stats.monetary_score >= 4, "still one of the biggest spenders"
    assert stats.frequency_score >= 4, "and one of the most frequent"
    assert stats.average_gap_days == 13.0
    assert stats.suggested_lifecycle == "at_risk"


def test_a_customer_who_orders_rarely_is_not_at_risk_for_being_rare():
    """Three weeks late means nothing to somebody who orders twice a year."""
    orders = [order(days_ago=day, total=3000) for day in (20, 200, 380)]

    stats = crm.summarise(orders, now=NOW)

    assert stats.average_gap_days == 180.0
    assert crm.has_gone_quiet(stats) is False


def test_a_single_purchase_then_a_month_of_silence_is_at_risk():
    """One order and no cadence to judge it by. The band has to decide."""
    assert crm.summarise([order(days_ago=45, total=1200)], now=NOW).suggested_lifecycle == "at_risk"


def test_four_months_of_silence_is_lost():
    stats = crm.summarise([order(days_ago=200, total=5000)], now=NOW)

    assert stats.recency_score == 1
    assert stats.suggested_lifecycle == "lost"


def test_a_handful_of_recent_orders_is_regular():
    orders = [order(days_ago=day, total=900) for day in (2, 9, 16)]

    assert crm.summarise(orders, now=NOW).suggested_lifecycle == "regular"


def test_the_revenue_series_keeps_the_days_nobody_ordered():
    """A chart that skips quiet days draws a busy week over a quiet fortnight."""
    series = crm.revenue_by_day([order(days_ago=0, total=1000)], days=7, now=NOW)

    assert len(series) == 7
    assert [point["day"] for point in series] == sorted(point["day"] for point in series)
    assert sum(point["revenue"] for point in series) == 1000
    assert sum(1 for point in series if point["revenue"] == 0) == 6


def test_top_products_price_a_line_that_carries_no_subtotal():
    orders = [
        order(days_ago=1, total=2400, items=[
            {"name": "Shin Ramyun — 5 Pack", "quantity": 2, "unit_price": 1200},
            {"name": "Kimchi 500g", "quantity": 1, "subtotal": 950},
        ])
    ]

    ranked = {row["name"]: row for row in crm.top_products(orders)}

    assert ranked["Shin Ramyun — 5 Pack"]["revenue"] == 2400
    assert ranked["Kimchi 500g"]["revenue"] == 950


def test_a_customer_whose_first_order_is_in_the_window_counts_once():
    """Their second order that same week must not make them returning as well."""
    orders = [order(days_ago=3, total=1000), order(days_ago=1, total=1000)]

    split = crm.new_versus_returning(orders, days=30, now=NOW)

    assert split["new_customers"] == 1
    assert split["returning_customers"] == 0


def test_a_customer_from_before_the_window_counts_as_returning():
    orders = [
        order(days_ago=200, total=1000),
        order(days_ago=2, total=1000),
    ]

    split = crm.new_versus_returning(orders, days=30, now=NOW)

    assert split["new_customers"] == 0
    assert split["returning_customers"] == 1


def test_totals_carry_the_period_before_them_to_compare():
    orders = [order(days_ago=5, total=1000), order(days_ago=40, total=4000)]

    figures = crm.totals(orders, days=30, now=NOW)

    assert figures["current"]["revenue"] == 1000
    assert figures["previous"]["revenue"] == 4000


# ---------------------------------------------------------------------------
# The HTTP surface
# ---------------------------------------------------------------------------
@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


@pytest.fixture
def wired(monkeypatch):
    fake = FakeSupabase()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)

    fake.seed(
        "businesses",
        [{"id": BUSINESS_ID, "name": "K FOOD", "wa_phone_number_id": "PNID", "profile": {}}],
    )
    fake.seed(
        "contacts",
        [
            {
                "id": CONTACT_ID,
                "business_id": BUSINESS_ID,
                "wa_id": "94771234567",
                "name": "Nimal",
                "language": "en",
                "tags": [],
                "lifecycle": "lead",
                "unread_count": 3,
                "human_takeover": False,
                "last_customer_message_at": None,
                "last_seen": "2026-09-19T09:00:00+00:00",
            },
            {
                "id": OTHER_ID,
                "business_id": BUSINESS_ID,
                "wa_id": "94770000000",
                "name": "Kasun",
                "language": "en",
                "tags": [],
                "lifecycle": "vip",
                "unread_count": 0,
                "human_takeover": False,
                "last_customer_message_at": None,
                "last_seen": "2026-09-18T09:00:00+00:00",
            },
        ],
    )
    fake.seed(
        "orders",
        [
            order(days_ago=2, total=2400),
            order(days_ago=9, total=1200),
            order(days_ago=4, total=3000, contact_id=OTHER_ID, source="pos"),
        ],
    )
    return fake


def test_the_customer_list_joins_stats_onto_each_contact(client, wired):
    body = client.get("/crm/customers").json()

    by_name = {row["contact"]["name"]: row for row in body["customers"]}
    assert by_name["Nimal"]["stats"]["orders"] == 2
    assert by_name["Nimal"]["stats"]["lifetime_value"] == 3600
    assert by_name["Kasun"]["stats"]["orders"] == 1
    assert body["segments"] == {"lead": 1, "vip": 1}


def test_the_customer_list_can_be_searched_by_number(client, wired):
    body = client.get("/crm/customers", params={"search": "94770000000"}).json()

    assert [row["contact"]["name"] for row in body["customers"]] == ["Kasun"]


def test_a_customer_detail_carries_orders_notes_tasks_and_messages(client, wired):
    client.post(f"/crm/customers/{CONTACT_ID}/notes", json={"note": "Prefers evening delivery"})
    client.post("/crm/tasks", json={"title": "Call about the bulk order", "contact_id": CONTACT_ID})

    body = client.get(f"/crm/customers/{CONTACT_ID}").json()

    assert body["contact"]["name"] == "Nimal"
    assert len(body["orders"]) == 2
    assert body["notes"][0]["note"] == "Prefers evening delivery"
    assert body["tasks"][0]["title"] == "Call about the bulk order"
    assert body["window_open"] is False, "this contact has never messaged us"


def test_an_unknown_customer_is_a_404(client, wired):
    assert client.get("/crm/customers/44444444-4444-4444-4444-444444444444").status_code == 404


def test_an_edit_saves_only_the_fields_that_were_sent(client, wired):
    client.patch(f"/crm/customers/{CONTACT_ID}", json={"city": "Kurunegala"})

    contact = next(c for c in wired.rows("contacts") if c["id"] == CONTACT_ID)
    assert contact["city"] == "Kurunegala"
    assert contact["name"] == "Nimal", "a field nobody sent must not be cleared"


def test_an_edit_cannot_reach_the_agents_own_columns(client, wired):
    """unread_count and the 24-hour window belong to the webhook, not to staff."""
    res = client.patch(
        f"/crm/customers/{CONTACT_ID}",
        json={"city": "Kandy", "unread_count": 0, "last_customer_message_at": "2026-09-19T00:00:00Z"},
    )

    assert res.status_code == 200
    contact = next(c for c in wired.rows("contacts") if c["id"] == CONTACT_ID)
    assert contact["city"] == "Kandy"
    assert contact["unread_count"] == 3, "still whatever the webhook last set"
    assert contact["last_customer_message_at"] is None


def test_an_edit_with_nothing_in_it_is_refused(client, wired):
    assert client.patch(f"/crm/customers/{CONTACT_ID}", json={}).status_code == 400


def test_a_note_is_saved_against_the_staff_member_not_the_agent(client, wired):
    """The agent reads this table when it answers, so authorship has to be true."""
    res = client.post(f"/crm/customers/{CONTACT_ID}/notes", json={"note": "Allergic to shellfish"})

    assert res.status_code == 200
    assert res.json()["note"]["created_by"] == "dev@local"
    assert res.json()["note"]["pinned"] is False


def test_a_pinned_note_comes_back_first_however_old_it_is(client, wired):
    client.post(
        f"/crm/customers/{CONTACT_ID}/notes",
        json={"note": "Allergic to shellfish", "pinned": True},
    )
    client.post(f"/crm/customers/{CONTACT_ID}/notes", json={"note": "Asked about Buldak"})

    notes = client.get(f"/crm/customers/{CONTACT_ID}").json()["notes"]

    assert notes[0]["note"] == "Allergic to shellfish"
    assert notes[0]["pinned"] is True


def test_a_note_can_be_unpinned_afterwards(client, wired):
    created = client.post(
        f"/crm/customers/{CONTACT_ID}/notes", json={"note": "Pays on delivery", "pinned": True}
    ).json()["note"]

    res = client.patch(f"/crm/notes/{created['id']}", json={"pinned": False})

    assert res.status_code == 200
    assert res.json()["note"]["pinned"] is False


def test_a_task_is_open_until_it_is_ticked_off(client, wired):
    created = client.post(
        "/crm/tasks",
        json={"title": "Chase the Kurunegala delivery", "contact_id": CONTACT_ID, "priority": "high"},
    ).json()["task"]

    assert client.get("/crm/tasks").json()["open_count"] == 1

    done = client.patch(f"/crm/tasks/{created['id']}", json={"done": True}).json()["task"]

    assert done["done_at"] is not None
    assert done["done_by"] == "dev@local"
    assert client.get("/crm/tasks").json()["open_count"] == 0
    assert len(client.get("/crm/tasks", params={"state": "done"}).json()["tasks"]) == 1


def test_a_task_can_be_reopened_and_forgets_who_closed_it(client, wired):
    created = client.post("/crm/tasks", json={"title": "Call the supplier"}).json()["task"]
    client.patch(f"/crm/tasks/{created['id']}", json={"done": True})

    reopened = client.patch(f"/crm/tasks/{created['id']}", json={"done": False}).json()["task"]

    assert reopened["done_at"] is None
    assert reopened["done_by"] is None


def test_an_overdue_task_is_counted_as_overdue(client, wired):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    client.post("/crm/tasks", json={"title": "Ring back about the refund", "due_at": past})
    client.post("/crm/tasks", json={"title": "Someday: reorder shelf labels"})

    body = client.get("/crm/tasks").json()

    assert body["open_count"] == 2
    assert body["overdue_count"] == 1
    assert body["tasks"][0]["title"] == "Ring back about the refund", "dated before undated"


def test_a_task_for_an_unknown_customer_is_refused(client, wired):
    res = client.post(
        "/crm/tasks", json={"title": "Call them", "contact_id": "44444444-4444-4444-4444-444444444444"}
    )

    assert res.status_code == 404


def test_a_task_with_a_blank_title_is_refused(client, wired):
    assert client.post("/crm/tasks", json={"title": "   "}).status_code == 400


def test_analytics_reports_revenue_the_mix_and_the_month(client, wired):
    body = client.get("/crm/analytics", params={"days": 30}).json()

    assert body["days"] == 30
    assert body["totals"]["current"]["orders"] == 3
    assert body["totals"]["current"]["revenue"] == 6600
    assert len(body["revenue_by_day"]) == 30
    assert {row["key"] for row in body["source_mix"]} == {"agent", "pos"}
    assert body["segments"] == {"lead": 1, "vip": 1}
    assert "outbound" in body["messages"]


def test_analytics_refuses_a_window_it_cannot_serve(client, wired):
    assert client.get("/crm/analytics", params={"days": 5000}).status_code == 422


# ---------------------------------------------------------------------------
# Invoices — the gap Phase 2 left open
# ---------------------------------------------------------------------------
@pytest.fixture
def billed(wired):
    wired.seed(
        "order_invoices",
        [
            {
                "id": "invoice-1",
                "business_id": BUSINESS_ID,
                "order_id": "order-2-2400-2222",
                "device_id": "MAC1",
                "bill_no": "KF-MAC1-20260919-003",
                "printed_at": "2026-09-19T08:00:00+00:00",
                "paper_total": 2600,
                "server_total": 2400,
                "mismatch": True,
                "mismatch_detail": [{"sku": "RAM-SHIN-5", "printed": 1300, "server": 1200}],
                "reviewed_at": None,
                "reviewed_by": None,
                "created_by": "pos:MAC1",
            }
        ],
    )
    return wired


def test_staff_can_finally_see_the_printed_bills(client, billed):
    body = client.get("/crm/invoices").json()

    assert body["invoices"][0]["bill_no"] == "KF-MAC1-20260919-003"
    assert body["mismatch_count"] == 1


def test_reviewing_a_mismatch_records_who_looked_and_changes_no_figure(client, billed):
    """The paper in the parcel says what it says. Reviewing is not correcting."""
    res = client.post("/crm/invoices/invoice-1/review")

    assert res.status_code == 200
    invoice = res.json()["invoice"]
    assert invoice["reviewed_by"] == "dev@local"
    assert invoice["reviewed_at"] is not None
    assert invoice["paper_total"] == 2600
    assert invoice["server_total"] == 2400
    assert client.get("/crm/invoices").json()["mismatch_count"] == 0


def test_reviewing_an_unknown_invoice_is_a_404(client, billed):
    assert client.post("/crm/invoices/nope/review").status_code == 404


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------
def test_a_pos_device_cannot_read_the_customer_book(client, wired, monkeypatch):
    """The shop Mac sits on a shared counter. It must not hold the CRM."""
    raw = "kfpos_test_token_for_the_shop_mac"
    wired.seed(
        "device_tokens",
        [
            {
                "id": "device-1",
                "business_id": BUSINESS_ID,
                "device_id": "MAC1",
                "name": "Shop Mac",
                "token_prefix": raw[:14],
                "token_hash": db.devices.hash_token(raw),
                "scopes": ["catalog", "orders"],
                "revoked_at": None,
            }
        ],
    )
    monkeypatch.setattr(config.settings, "require_auth", True)
    monkeypatch.setattr(main.settings, "require_auth", True, raising=False)
    auth._device_cache.clear()
    auth._device_seen.clear()

    headers = {"X-Device-Token": raw}
    assert client.get("/crm/customers", headers=headers).status_code == 401
    assert client.get("/crm/analytics", headers=headers).status_code == 401
    assert client.get("/crm/invoices", headers=headers).status_code == 401
    assert client.post(
        "/crm/tasks", headers=headers, json={"title": "anything"}
    ).status_code == 401
