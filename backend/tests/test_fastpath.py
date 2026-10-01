"""Replies that need no model: the ad opener and a bare "price?"."""

from __future__ import annotations

import asyncio

import pytest

import db
import handlers
from fastpath import classify, fast_reply, language
from tests.conftest import BUSINESS_ID
from tests.fakes import seed_kfood
from tests.test_handlers import inbound
from tests.test_handlers import wired as handler_env  # noqa: F401 — a fixture


@pytest.fixture
def wired(handler_env):  # noqa: F811
    fake, wa, calls = handler_env
    db.business.clear_cache()
    seed_kfood(fake, BUSINESS_ID)
    return fake, wa, calls


@pytest.mark.parametrize(
    "texts",
    [
        ["Hi! I want to order Korean ramen 🍜"],
        ["Hi! I want to order Korean ramen 🍜  👍🤙"],
        ["Hi! How  to order Korean ramen 🍜"],
    ],
)
def test_the_ad_opener_is_answered_by_code(texts):
    assert classify(texts) == "ad_opener"


@pytest.mark.parametrize(
    "texts",
    [
        ["Price"], ["Kiyada"], ["price list plz"], ["Price list ek ewnna"], ["මිල ගනන්"],
        ["How much"], ["Send me all prices"], ["Parice and menu plz"],
        ["How much a Korean ramen 🍜 ?"],
        ["Hi! I want to order Korean ramen 🍜කීයද"],
        ["Hi! I want to order Korean ramen 🍜", "Price"],
    ],
)
def test_a_bare_price_question_is_answered_by_code(texts):
    assert classify(texts) == "price_question"


@pytest.mark.parametrize(
    "texts",
    [
        ["Shin ramen noodles price kohomada"],          # names a product
        ["5packs price shin Ramyun"],
        ["Kiyada mewa"],                                # "these" — a photo
        ["Deliver kurunegala"],
        ["Hi"],
        ["Hi! I want to order Korean ramen 🍜", "Shin Black price?"],
        ["How much is 5 pack and deliver charge to kadawatha"],
        [],
    ],
)
def test_anything_else_goes_to_the_agent(texts):
    assert classify(texts) is None


def test_the_closing_line_follows_the_customer_s_language():
    assert language(["මිල ගනන්"]) == "si"
    assert language(["Price list ek ewnna"]) == "singlish"
    assert language(["Price list please"]) == "en"


async def test_the_opener_gets_the_noodles_and_a_price_question_gets_everything(wired):
    opener = await fast_reply(BUSINESS_ID, ["Hi! I want to order Korean ramen 🍜"])
    price = await fast_reply(BUSINESS_ID, ["Kiyada"])

    assert opener.reason == "ad_opener"
    assert opener.text.startswith("Hi! 😊 Here are our Korean noodles:")
    assert "Shin Ramyun Original — *Rs. 650*" in opener.text
    assert "Banana" not in opener.text
    assert price.reason == "price_question"
    assert "Binggrae Banana Flavoured Milk" in price.text
    assert price.text.endswith("select karala dennam 🌶️")


async def test_the_handler_sends_it_without_calling_the_model(wired):
    fake, wa, calls = wired

    await handlers.process_inbound(inbound("Price list ek ewnna", "wamid.PL"), BUSINESS_ID)

    assert calls == [], "the model was not called"
    [(_, body)] = wa.texts
    assert "*K FOOD Price List*" in body
    [usage] = fake.rows("llm_usage")
    assert usage["model"] == "code" and usage["cost_usd"] == 0


async def test_an_opener_with_a_product_question_goes_to_the_agent(wired, monkeypatch):
    fake, wa, calls = wired
    monkeypatch.setattr(handlers.settings, "reply_batch_seconds", 0.05)

    await asyncio.gather(
        handlers.process_inbound(inbound("Hi! I want to order Korean ramen 🍜", "wamid.O"), BUSINESS_ID),
        handlers.process_inbound(inbound("Shin Black price?", "wamid.Q"), BUSINESS_ID),
    )

    assert calls == ["Shin Black price?"]


async def test_a_photo_in_the_burst_goes_to_the_agent(wired, monkeypatch):
    from tests.test_handlers import ImageAnalysis

    fake, wa, calls = wired

    async def describe(media, *, catalogue):
        return ImageAnalysis(kind="product", description="a red noodle pack")

    monkeypatch.setattr(handlers, "describe_image", describe)
    wa.media_downloads["m1"] = __import__("whatsapp").DownloadedMedia(
        content=b"x", mime_type="image/jpeg", filename="p.jpg"
    )

    await handlers.process_inbound(
        inbound("price?", "wamid.IMG", mtype="image", media_id="m1", media_mime="image/jpeg"),
        BUSINESS_ID,
    )

    assert calls == ["price?"]
