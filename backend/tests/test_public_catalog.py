"""The unauthenticated catalogue, and the one thing it must never say.

`menu_items` carries `stock_quantity` on every row. These routes are served to
anyone who curls them, so a dict passthrough would publish the shop's stock
levels — which tell a competitor its sales volume — to the open internet.

The leak test below searches the whole serialized body rather than checking
named fields, because the failure this guards against is a field nobody
remembered to think about.
"""

from __future__ import annotations

import json

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


def track(fake, sku, quantity):
    for row in fake.tables["menu_items"]:
        if row["sku"] == sku:
            row["track_stock"] = True
            row["stock_quantity"] = quantity
            return
    raise AssertionError(f"{sku} not seeded")


# --- the leak test ---------------------------------------------------------

def test_the_public_catalogue_never_mentions_stock(client, wired):
    track(wired, "RAM-SHIN-1", 4242)
    body = client.get("/public/catalog").json()
    raw = json.dumps(body)
    assert "4242" not in raw
    assert "stock_quantity" not in raw
    assert "track_stock" not in raw


def test_public_availability_never_mentions_stock(client, wired):
    track(wired, "RAM-SHIN-1", 4242)
    raw = json.dumps(client.get("/public/availability").json())
    assert "4242" not in raw
    assert "stock_quantity" not in raw


def test_the_public_catalogue_needs_no_token(client, wired):
    assert client.get("/public/catalog").status_code == 200
    assert client.get("/public/availability").status_code == 200


# --- shape -----------------------------------------------------------------

def test_the_catalogue_carries_products_and_prices(client, wired):
    body = client.get("/public/catalog").json()
    assert len(body["products"]) == 3
    shin = next(p for p in body["products"] if p["handle"] == "shin-ramyun")
    assert {v["sku"] for v in shin["variants"]} == {"RAM-SHIN-1", "RAM-SHIN-5", "RAM-SHIN-20"}
    assert next(v for v in shin["variants"] if v["sku"] == "RAM-SHIN-1")["price"] == 650


def test_the_store_block_replaces_what_the_site_hardcodes(client, wired):
    store = client.get("/public/catalog").json()["store"]
    assert store["delivery_fee"] == 400
    assert store["free_delivery_threshold"] == 5000
    # The site currently hardcodes this string in its OnlineStore markup.
    assert store["price_range"] == "LKR 590 – LKR 15,000"
    assert store["bank"]


# --- availability ----------------------------------------------------------

def test_an_untracked_product_is_in_stock(client, wired):
    """Nothing changes on the day this ships: no product is tracked yet."""
    items = client.get("/public/availability").json()["items"]
    assert {i["state"] for i in items} == {"in_stock"}


def test_a_product_with_no_stock_is_out(client, wired):
    track(wired, "RAM-SHIN-1", 0)
    items = client.get("/public/availability").json()["items"]
    shin = {i["sku"]: i["state"] for i in items if i["sku"].startswith("RAM-SHIN")}
    assert shin == {"RAM-SHIN-1": "out_of_stock", "RAM-SHIN-5": "out_of_stock",
                    "RAM-SHIN-20": "out_of_stock"}


def test_a_pack_needs_enough_singles_to_make_it(client, wired):
    """Stock is counted in singles: four of them cannot make a 5 Pack."""
    track(wired, "RAM-SHIN-1", 4)
    items = {i["sku"]: i["state"] for i in client.get("/public/availability").json()["items"]}
    assert items["RAM-SHIN-1"] == "in_stock"
    assert items["RAM-SHIN-5"] == "out_of_stock"
    assert items["RAM-SHIN-20"] == "out_of_stock"


def test_availability_has_two_states_and_no_third(client, wired):
    track(wired, "RAM-SHIN-1", 2)
    states = {i["state"] for i in client.get("/public/availability").json()["items"]}
    assert states <= {"in_stock", "out_of_stock"}


# --- caching ---------------------------------------------------------------

def test_the_catalogue_carries_an_etag_and_cache_control(client, wired):
    res = client.get("/public/catalog")
    assert res.headers["etag"]
    assert "max-age" in res.headers["cache-control"]


def test_the_etag_is_stable_across_calls(client, wired):
    first = client.get("/public/catalog").headers["etag"]
    catalog.clear_cache()
    second = client.get("/public/catalog").headers["etag"]
    assert first == second, "a timestamp must not feed the hash"


def test_a_matching_etag_returns_304_with_no_body(client, wired):
    etag = client.get("/public/catalog").headers["etag"]
    res = client.get("/public/catalog", headers={"If-None-Match": etag})
    assert res.status_code == 304
    assert not res.content


def test_a_price_change_changes_the_etag(client, wired):
    first = client.get("/public/catalog").headers["etag"]
    for row in wired.tables["menu_items"]:
        if row["sku"] == "RAM-SHIN-1":
            row["price"] = 700
    catalog.clear_cache()
    assert client.get("/public/catalog").headers["etag"] != first


def test_availability_revalidates_too(client, wired):
    etag = client.get("/public/availability").headers["etag"]
    assert client.get("/public/availability",
                      headers={"If-None-Match": etag}).status_code == 304


# --- the POS sees more than the public does --------------------------------

def test_the_pos_catalogue_does_carry_stock(client, wired):
    """Staff pricing a parcel should see the shelf; the public should not."""
    track(wired, "RAM-SHIN-1", 42)
    body = client.get("/pos/catalog").json()
    shin = next(p for p in body["products"] if p["handle"] == "shin-ramyun")
    assert shin["track_stock"] is True
    assert shin["stock_quantity"] == 42
