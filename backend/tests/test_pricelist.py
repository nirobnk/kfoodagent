"""The price list the agent sends when someone asks for prices without naming a product."""

from __future__ import annotations

import pytest

import db
from agent.prompts import build_system_prompt
from agent.state import RunContext
from agent.tools import price_list
from agent.tools.pricelist import build_price_list, heat_marks
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

PROFILE = {"delivery": {"fee": 400, "freeDeliveryThreshold": 5000}}


def product(name: str, category: str, price: float, heat=None, badge=None, **extra) -> dict:
    return {
        "product_name": name, "category": category, "heat_level": heat, "badge": badge,
        "variants": [
            {"label": "Single Pack", "price": price, "sku": f"{name}-1", "units": 1},
            {"label": "5 Pack", "price": price * 5, "sku": f"{name}-5", "units": 5},
        ],
        **extra,
    }


CATALOGUE = [
    product("Shin Ramyun Original", "Instant Noodles", 650, heat=4, badge="Best Seller"),
    product("Hot Dak Stir-Fry Ramen Original", "Instant Noodles", 750, heat=5),
    product("Chapagetti", "Instant Noodles", 750, heat=0),
    product("Shin Ramyun Cup", "Cup Noodles", 560, heat=4),
    product("OKF Olatte Apple", "Beverages", 690, badge="New"),
    product("Bacchus Energy Drink", "Beverages", 690),
]


def test_the_list_is_grouped_marked_and_priced():
    text = build_price_list(CATALOGUE, PROFILE)

    assert text.startswith("🇰🇷 *K FOOD Price List* 🍜")
    assert "🍜 *Shin Ramyun*\n• Shin Ramyun Original — *Rs. 650* 🌶️🌶️🌶️ ⭐" in text
    assert "🔥 *Hot Dak Fire Noodles*\n• Hot Dak Stir-Fry Ramen Original — *Rs. 750* 🔥🔥🔥" in text
    assert "• Chapagetti — *Rs. 750* (no spice)" in text
    assert "🥡 *Cup Noodles*" in text
    assert "• OKF Olatte Apple — *Rs. 690* 🆕" in text
    assert "🌶️ spice level · 🔥 extra hot · ⭐ customer favourite · 🆕 new" in text
    assert "📦 5 Pack = 5 × price" in text
    assert "🚚 Island-wide delivery Rs. 400 · *FREE* over Rs. 5,000" in text


def test_every_product_is_on_it():
    """Twenty products was the old cap; the ten drinks past it were never listed."""
    many = CATALOGUE + [product(f"OKF Oncup {i}", "Beverages", 760) for i in range(30)]

    text = build_price_list(many, PROFILE)

    assert all(f"OKF Oncup {i} —" in text for i in range(30))


def test_a_section_lists_only_what_they_asked_about():
    drinks = build_price_list(CATALOGUE, PROFILE, section="drinks")
    noodles = build_price_list(CATALOGUE, PROFILE, section="noodles")

    assert "Bacchus" in drinks and "Shin Ramyun" not in drinks
    assert "Shin Ramyun Cup" in noodles and "Bacchus" not in noodles


def test_an_empty_shelf_is_struck_through_not_sold():
    gone = product("Kimchi Ramyun", "Instant Noodles", 750, heat=3, track_stock=True,
                   stock_quantity=0)

    text = build_price_list([gone], PROFILE)

    assert "• Kimchi Ramyun — ~Rs. 750~ ❌ out of stock" in text


def test_packs_priced_off_the_rule_are_not_promised_at_it():
    odd = product("Shin Ramyun Black", "Instant Noodles", 895, heat=3)
    odd["variants"][1]["price"] = 4000

    text = build_price_list([odd], PROFILE)

    assert "5 × price" not in text
    assert "📦 5 Packs and cartons of 20 too — just ask" in text


def test_heat_never_takes_more_than_three_marks():
    assert heat_marks(None) == ""
    assert heat_marks(1) == " 🌶️"
    assert heat_marks(4) == " 🌶️🌶️🌶️"
    assert heat_marks(5) == " 🔥🔥🔥"


@pytest.fixture
def tool_env(monkeypatch):
    fake = FakeSupabase()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)
    db.business.clear_cache()
    seed_kfood(fake, BUSINESS_ID)
    ctx = RunContext(business_id=BUSINESS_ID, contact={"id": "c", "wa_id": "9477"})
    return ctx, {"configurable": {"run_context": ctx}}


async def test_the_tool_hands_over_the_block_to_send_as_it_is(tool_env):
    ctx, config = tool_env

    result = await price_list.ainvoke({}, config=config)

    assert "EXACTLY as it is laid out" in result
    assert "*K FOOD Price List*" in result
    assert "Binggrae Banana Flavoured Milk" in result
    assert ctx.tools_called == ["price_list"]


def test_the_prompt_sends_the_price_list_for_a_price_question():
    prompt = build_system_prompt(business_name="K FOOD", contact={"name": "Nimal"})

    assert "call price_list" in prompt
    assert "except in the price_list block" in prompt
