"""Stock: a ledger whose sum is the quantity, and the guards around it."""

from __future__ import annotations

import pytest

import db
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

CONTACT_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def stock(monkeypatch):
    fake = FakeSupabase()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)

    db.business.clear_cache()
    seed_kfood(fake, BUSINESS_ID)
    item = next(r for r in fake.rows("menu_items") if r.get("sku") == "RAM-SHIN-1")
    item["track_stock"] = True
    item["stock_quantity"] = 0
    return fake, item


async def test_the_quantity_is_the_sum_of_its_movements(stock):
    fake, item = stock

    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=24, reason="received"
    )
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=-2, reason="damaged"
    )

    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 22
    ledger = await db.inventory.movements(BUSINESS_ID, menu_item_id=item["id"])
    assert sum(m["delta"] for m in ledger) == 22


async def test_a_movement_of_zero_is_refused(stock):
    _, item = stock

    with pytest.raises(ValueError, match="zero"):
        await db.inventory.record(
            business_id=BUSINESS_ID, menu_item_id=item["id"], delta=0, reason="adjusted"
        )


async def test_an_unknown_reason_is_refused(stock):
    _, item = stock

    with pytest.raises(ValueError, match="unknown inventory reason"):
        await db.inventory.record(
            business_id=BUSINESS_ID, menu_item_id=item["id"], delta=1, reason="borrowed"
        )


async def test_a_stocktake_records_the_difference_not_the_number(stock):
    """The ledger must keep saying how stock changed, or it stops reconciling."""
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=10, reason="received"
    )

    movement = await db.inventory.set_count(
        business_id=BUSINESS_ID, menu_item_id=item["id"], counted=7
    )

    assert movement["delta"] == -3
    assert movement["reason"] == "count"
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 7


async def test_a_stocktake_that_agrees_records_nothing(stock):
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=5, reason="received"
    )

    assert await db.inventory.set_count(
        business_id=BUSINESS_ID, menu_item_id=item["id"], counted=5
    ) is None
    assert len(await db.inventory.movements(BUSINESS_ID, menu_item_id=item["id"])) == 1


# --- orders ---------------------------------------------------------------

def an_order(item, quantity=2, order_id="order-1"):
    return {
        "id": order_id,
        "business_id": BUSINESS_ID,
        "order_number": 7,
        "items": [{"sku": item["sku"], "menu_item_id": item["id"], "quantity": quantity}],
    }


async def test_confirming_an_order_takes_the_stock(stock):
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=5, reason="received"
    )

    sold = await db.inventory.sell_order(an_order(item))

    assert sold == ["RAM-SHIN-1"]
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 3


async def test_confirming_twice_does_not_sell_the_stock_twice(stock):
    """An order can go confirmed -> preparing -> confirmed from the dashboard."""
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=5, reason="received"
    )
    order = an_order(item)

    await db.inventory.sell_order(order)
    again = await db.inventory.sell_order(order)

    assert again == []
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 3


async def test_an_untracked_product_is_never_decremented(stock):
    """Untracked means unlimited, exactly as before stock existed."""
    fake, item = stock
    item["track_stock"] = False

    sold = await db.inventory.sell_order(an_order(item))

    assert sold == []
    assert fake.rows("inventory_movements") == []


async def test_cancelling_puts_the_stock_back(stock):
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=5, reason="received"
    )
    order = an_order(item)
    await db.inventory.sell_order(order)

    restored = await db.inventory.restock_order(order)

    assert restored == [item["id"]]
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 5


async def test_cancelling_twice_does_not_invent_stock(stock):
    _, item = stock
    await db.inventory.record(
        business_id=BUSINESS_ID, menu_item_id=item["id"], delta=5, reason="received"
    )
    order = an_order(item)
    await db.inventory.sell_order(order)
    await db.inventory.restock_order(order)

    assert await db.inventory.restock_order(order) == []
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 5


async def test_cancelling_an_order_that_never_sold_anything_is_harmless(stock):
    _, item = stock

    assert await db.inventory.restock_order(an_order(item)) == []
    assert await db.inventory.quantity(BUSINESS_ID, item["id"]) == 0
