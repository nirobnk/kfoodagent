"""Agent behaviour that does not need an LLM: tools, prompt, reply cleaning."""

from __future__ import annotations

import pytest

import db
from agent.graph import clean_reply
from agent.prompts import build_system_prompt
from agent.state import RunContext
from agent.tools import (
    create_order,
    escalate_to_human,
    product_details,
    save_note,
    search_menu,
    send_product_photo,
    store_info,
)
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, seed_kfood

CONTACT = {
    "id": "22222222-2222-2222-2222-222222222222",
    "business_id": BUSINESS_ID,
    "wa_id": "94771234567",
    "name": "Nimal",
    "language": "en",
    "tags": ["regular"],
}


@pytest.fixture
def tool_env(monkeypatch):
    fake = FakeSupabase()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)

    db.business.clear_cache()
    seed_kfood(fake, BUSINESS_ID)

    ctx = RunContext(business_id=BUSINESS_ID, contact=dict(CONTACT))
    return fake, ctx, {"configurable": {"run_context": ctx}}


# --- catalogue ------------------------------------------------------------

async def test_search_menu_returns_every_variant_price_and_sku(tool_env):
    _, ctx, config = tool_env

    result = await search_menu.ainvoke({"query": "shin ramyun"}, config=config)

    assert "Shin Ramyun Original" in result
    assert "Nongshim" in result
    assert "Single Pack Rs. 650 [RAM-SHIN-1]" in result
    assert "5 Pack Rs. 3,250 [RAM-SHIN-5]" in result
    assert "Carton (20) Rs. 13,000 [RAM-SHIN-20]" in result
    assert "heat 4/5" in result
    assert ctx.tools_called == ["search_menu"]


async def test_search_menu_finds_a_product_by_brand_or_category(tool_env):
    _, _, config = tool_env

    by_brand = await search_menu.ainvoke({"query": "binggrae"}, config=config)
    assert "Banana Flavoured Milk" in by_brand

    by_category = await search_menu.ainvoke({"query": "beverages"}, config=config)
    assert "Banana Flavoured Milk" in by_category


async def test_search_menu_empty_query_lists_the_catalogue(tool_env):
    _, _, config = tool_env

    result = await search_menu.ainvoke({"query": ""}, config=config)

    assert "Shin Ramyun Original" in result
    assert "Hot Dak Stir Fry Ramen Original" in result
    assert "Binggrae Banana Flavoured Milk" in result


async def test_search_menu_reports_no_match_plainly(tool_env):
    _, _, config = tool_env
    result = await search_menu.ainvoke({"query": "pizza"}, config=config)
    assert "Nothing on the catalogue matches" in result


async def test_product_details_quotes_allergens_and_cooking(tool_env):
    _, ctx, config = tool_env

    result = await product_details.ainvoke({"product": "Shin Ramyun Original"}, config=config)

    assert "Contains wheat, soy and beef" in result
    assert "4-5 mins" in result
    assert "Boil 550ml" in result
    assert "520 kcal" in result
    assert ctx.tools_called == ["product_details"]


async def test_product_details_on_an_unknown_product(tool_env):
    _, _, config = tool_env
    result = await product_details.ainvoke({"product": "Sushi Platter"}, config=config)
    assert "No product called" in result


# --- the shop -------------------------------------------------------------

async def test_store_info_answers_delivery_questions_from_the_profile(tool_env):
    _, ctx, config = tool_env

    result = await store_info.ainvoke(
        {"question": "do you deliver to Jaffna and how long does it take?"}, config=config
    )

    assert "Rs. 400" in result
    assert "5,000" in result
    assert "2-4 days" in result
    assert "Never promise a delivery date" in result
    assert ctx.tools_called == ["store_info"]


async def test_store_info_answers_payment_questions_with_the_bank_details(tool_env):
    _, _, config = tool_env

    result = await store_info.ainvoke({"question": "how can I pay? card ekak ganna puluwanda?"},
                                      config=config)

    assert "Hatton National Bank" in result
    assert "123020163895" in result
    assert "no card payment" in result


async def test_store_info_answers_returns_questions(tool_env):
    _, _, config = tool_env
    result = await store_info.ainvoke({"question": "it arrived damaged"}, config=config)
    assert "7 days" in result


async def test_store_info_falls_back_to_the_basics(tool_env):
    _, _, config = tool_env
    result = await store_info.ainvoke({"question": "hello"}, config=config)
    assert "Delivery" in result and "Payment" in result


# --- orders ---------------------------------------------------------------

async def test_create_order_prices_variants_and_adds_delivery(tool_env):
    fake, ctx, config = tool_env

    result = await create_order.ainvoke(
        {
            "items": [{"sku": "RAM-SHIN-1", "quantity": 2}, {"sku": "DRK-BANANA-1", "quantity": 1}],
            "delivery_note": "12 Galle Road, Colombo 03",
        },
        config=config,
    )

    # 2 x 650 + 590 = 1,890, under the free-delivery threshold, so + Rs. 400.
    assert "Rs. 1,890" in result
    assert "delivery Rs. 400" in result
    assert "Rs. 2,290" in result

    order = fake.rows("orders")[0]
    assert order["subtotal"] == 1890
    assert order["delivery_fee"] == 400
    assert order["total"] == 2290
    assert order["notes"] == "12 Galle Road, Colombo 03"
    assert [i["sku"] for i in order["items"]] == ["RAM-SHIN-1", "DRK-BANANA-1"]
    assert ctx.created_order is not None


async def test_delivery_is_free_over_the_threshold(tool_env):
    fake, _, config = tool_env

    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SHIN-5", "quantity": 2}]}, config=config
    )

    assert "delivery free" in result
    order = fake.rows("orders")[0]
    assert order["subtotal"] == 6500
    assert order["delivery_fee"] == 0
    assert order["total"] == 6500


async def test_create_order_refuses_a_sku_that_does_not_exist(tool_env):
    fake, _, config = tool_env

    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SUSHI-1", "quantity": 1}]}, config=config
    )

    assert "not in the catalogue" in result
    assert fake.rows("orders") == [], "no order may be created from an invented SKU"


async def test_create_order_asks_for_an_address_when_none_was_given(tool_env):
    _, _, config = tool_env
    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SHIN-1", "quantity": 1}]}, config=config
    )
    assert "delivery address" in result


async def test_escalation_flips_the_takeover_flag(tool_env):
    fake, ctx, config = tool_env
    fake.seed("contacts", [dict(CONTACT, human_takeover=False)])

    result = await escalate_to_human.ainvoke({"reason": "wants a refund"}, config=config)

    assert ctx.escalated is True
    assert ctx.escalation_reason == "wants a refund"
    assert fake.rows("contacts")[0]["human_takeover"] is True
    assert "staff" in result.lower()
    assert any("refund" in n["note"] for n in fake.rows("notes"))


async def test_save_note_persists_and_ignores_noise(tool_env):
    fake, ctx, config = tool_env

    await save_note.ainvoke({"note": "Allergic to peanuts"}, config=config)
    await save_note.ainvoke({"note": "ok"}, config=config)

    notes = [n["note"] for n in fake.rows("notes")]
    assert notes == ["Allergic to peanuts"]
    assert ctx.notes_added == ["Allergic to peanuts"]


# --- prompt ---------------------------------------------------------------

def test_prompt_carries_customer_memory_and_open_order():
    prompt = build_system_prompt(
        business_name="K-Food",
        contact=CONTACT,
        notes=[{"note": "No spicy food"}],
        open_order={"order_number": 1043, "status": "preparing", "total": 2400,
                    "items": [{"name": "Shin Ramyun", "quantity": 2}]},
    )

    assert "K-Food" in prompt
    assert "Nimal" in prompt
    assert "No spicy food" in prompt
    assert "#1043" in prompt
    assert "2x Shin Ramyun" in prompt
    assert "search_menu" in prompt
    assert "ONE message" in prompt


def test_prompt_without_history_is_still_valid():
    prompt = build_system_prompt(business_name="K-Food", contact={"wa_id": "9477"})
    assert "unknown" in prompt
    assert "{" not in prompt.split("About this customer")[0][-80:]


# --- reply cleaning -------------------------------------------------------

def test_clean_reply_strips_markdown_for_whatsapp():
    assert clean_reply("## Menu\n- Shin Ramyun") == "Menu\n• Shin Ramyun"
    assert clean_reply("**Rs. 950**") == "*Rs. 950*"
    assert clean_reply("  spaced  ") == "spaced"
    assert clean_reply("a\n\n\n\nb") == "a\n\nb"


def test_clean_reply_caps_length():
    cleaned = clean_reply("word " * 400)
    assert len(cleaned) <= 901
    assert cleaned.endswith("…")


def test_clean_reply_handles_nothing():
    assert clean_reply("") == ""
    assert clean_reply(None) == ""


# --- search synonyms ------------------------------------------------------

def test_search_terms_expand_to_what_customers_actually_type():
    from db.menu import expand

    # The packs are spelled "Ramyun"; customers write "ramen".
    assert "ramyun" in expand("ramen")
    assert "noodle" in expand("ramen")
    assert "hot dak" in expand("buldak noodles")
    assert "beverages" in expand("drinks")
    assert expand("shin ramyun")[0] == "shin ramyun", "the original term stays first"
    assert expand("") == []


async def test_a_customer_asking_for_ramen_finds_ramyun(tool_env):
    _, _, config = tool_env

    result = await search_menu.ainvoke({"query": "ramen"}, config=config)

    assert "Shin Ramyun Original" in result


def test_a_truncated_search_tells_the_agent_to_say_how_many_are_missing():
    """A customer asked "is that all you have" and was told yes, while four
    products sat behind the truncation line. The line has to read as an
    instruction, not as a hint the model can take or leave."""
    from agent.tools.menu import MAX_PRODUCTS, format_products

    products = [
        {"product_name": f"Product {i}", "category": "Beverages", "variants": []}
        for i in range(MAX_PRODUCTS + 4)
    ]

    text = format_products(products)

    assert "+4 more products not shown" in text
    assert "NOT the full range" in text
    assert "tell the customer there are 4 more" in text


def test_a_complete_search_carries_no_truncation_notice():
    from agent.tools.menu import format_products

    text = format_products(
        [{"product_name": "Only One", "category": "Beverages", "variants": []}]
    )

    assert "more products" not in text


def test_the_prompt_forbids_claiming_a_list_is_complete():
    prompt = build_system_prompt(business_name="K FOOD", contact=CONTACT)

    assert "NEVER say or imply that a list is everything we sell" in prompt
    assert "is that all?" in prompt


# --- product photos -------------------------------------------------------

@pytest.fixture
def photo_env(tool_env, monkeypatch):
    """tool_env plus a recording stand-in for the outbound image send."""
    import outbound

    sent: list[dict] = []

    async def fake_send_image(*, business_id, contact, image_url, caption="", sender="agent"):
        sent.append({"image_url": image_url, "caption": caption})
        return outbound.SendResult(ok=True, wa_message_id=f"wamid.IMG{len(sent)}")

    monkeypatch.setattr(outbound, "send_image", fake_send_image)
    fake, ctx, config = tool_env
    return sent, ctx, config


async def test_send_product_photo_sends_the_catalogue_image(photo_env):
    sent, ctx, config = photo_env

    result = await send_product_photo.ainvoke(
        {"products": "Binggrae Banana Flavoured Milk"}, config=config
    )

    assert len(sent) == 1
    assert sent[0]["image_url"].startswith("https://kfoods.lk/")
    assert "Photo sent for" in result
    assert ctx.photos_sent == ["Binggrae Banana Flavoured Milk"]


async def test_send_product_photo_is_capped_so_a_reply_is_not_a_wall_of_images(photo_env):
    """Every photo is a paid message, so "show me everything" must not send 14."""
    from agent.tools.photos import MAX_PHOTOS

    sent, _, config = photo_env
    names = ", ".join(
        [
            "Binggrae Banana Flavoured Milk",
            "Binggrae Melon Flavoured Milk",
            "Binggrae Strawberry Flavoured Milk",
            "OKF Aloe Vera King",
            "Shin Ramyun Original",
        ]
    )

    await send_product_photo.ainvoke({"products": names}, config=config)

    assert len(sent) <= MAX_PHOTOS


async def test_an_unknown_product_is_reported_not_silently_skipped(photo_env):
    sent, _, config = photo_env

    result = await send_product_photo.ainvoke({"products": "Unicorn Ramyun"}, config=config)

    assert sent == []
    assert "Not on the catalogue" in result


async def test_no_product_named_asks_for_a_search_first(photo_env):
    sent, _, config = photo_env

    result = await send_product_photo.ainvoke({"products": "  "}, config=config)

    assert sent == []
    assert "search_menu" in result


def test_the_prompt_tells_it_to_send_photos_rather_than_the_website():
    prompt = build_system_prompt(business_name="K FOOD", contact=CONTACT)

    assert "send_product_photo" in prompt
    assert "never say you cannot send photos" in prompt


async def test_a_webp_photo_is_reported_missing_rather_than_failing(photo_env, monkeypatch):
    """WhatsApp treats .webp as a sticker and answers "Media upload error",
    which a customer saw. Skip it before spending the call."""
    import db as db_module

    sent, _, config = photo_env
    real = db_module.menu.get_product_detail

    async def webp_product(business_id, query):
        product = await real(business_id, query)
        if product:
            product["image_url"] = "https://kfoods.lk/images/shin-ramyun-pack.webp"
        return product

    monkeypatch.setattr(db_module.menu, "get_product_detail", webp_product)

    result = await send_product_photo.ainvoke(
        {"products": "Shin Ramyun Original"}, config=config
    )

    assert sent == []
    assert "No photo on file" in result


def test_the_prompt_asks_for_one_product_per_line_with_a_price():
    prompt = build_system_prompt(business_name="K FOOD", contact=CONTACT)

    assert "one product per line" in prompt
    assert "never drop the price" in prompt


def test_the_prompt_lets_the_agent_give_out_published_bank_details():
    """A customer asked for bank details twice, was told staff would send them,
    and the chat was escalated — while store_info already returned the account
    number that is printed on the shop's own checkout page."""
    prompt = build_system_prompt(business_name="K FOOD", contact=CONTACT)

    assert "GIVE them the bank, branch, account name and account number" in prompt
    assert "Do not escalate merely because someone asks for bank details" in prompt


# --- stock ----------------------------------------------------------------

async def test_create_order_refuses_to_sell_more_than_is_in_stock(tool_env):
    """The prompt can ask the agent not to oversell; only this can stop it."""
    fake, _, config = tool_env
    item = next(r for r in fake.rows("menu_items") if r["sku"] == "RAM-SHIN-1")
    item["track_stock"] = True
    item["stock_quantity"] = 3

    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SHIN-1", "quantity": 10}]}, config=config
    )

    assert "Not enough stock" in result
    assert "asked for 10, 3 in stock" in result
    assert fake.rows("orders") == []


async def test_create_order_still_sells_what_is_in_stock(tool_env):
    fake, _, config = tool_env
    item = next(r for r in fake.rows("menu_items") if r["sku"] == "RAM-SHIN-1")
    item["track_stock"] = True
    item["stock_quantity"] = 10

    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SHIN-1", "quantity": 2}]}, config=config
    )

    assert "created" in result.lower()
    assert len(fake.rows("orders")) == 1


async def test_an_untracked_product_has_no_stock_limit(tool_env):
    """Nothing changes for a product nobody is counting."""
    fake, _, config = tool_env
    item = next(r for r in fake.rows("menu_items") if r["sku"] == "RAM-SHIN-1")
    item["track_stock"] = False
    item["stock_quantity"] = 0

    result = await create_order.ainvoke(
        {"items": [{"sku": "RAM-SHIN-1", "quantity": 50}]}, config=config
    )

    assert "Not enough stock" not in result
    assert len(fake.rows("orders")) == 1


def test_search_menu_says_nothing_about_stock_it_does_not_track():
    from agent.tools.menu import stock_note

    assert stock_note({"track_stock": False, "stock_quantity": 0}) == ""
    assert "OUT OF STOCK" in stock_note({"track_stock": True, "stock_quantity": 0})
    assert "only 2 left" in stock_note({"track_stock": True, "stock_quantity": 2})
    assert stock_note({"track_stock": True, "stock_quantity": 99}) == ""
