"""Catalogue lookup. The only way the agent learns a price."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)

# The whole catalogue is around 20 products, so a cap of 12 truncated ordinary
# category questions like "what drinks do you have" (16 matches). Descriptions
# are already dropped above 6 products, so a full list stays cheap. Raise this
# with the catalogue; the "+N more" line below is what keeps it honest when a
# search does overflow.
MAX_PRODUCTS = 20

# At or below this the agent warns the customer, so a last pack is not promised
# to two people at once.
LOW_STOCK = 3


def money(value: Any) -> str:
    try:
        return f"Rs. {float(value):,.0f}"
    except (TypeError, ValueError):
        return f"Rs. {value}"


def variant_note(variant: dict[str, Any], product: dict[str, Any]) -> str:
    """Whether this pack can be made from the singles on the shelf.

    Stock is counted in singles, so a 5 Pack needs five of them. A pack that
    cannot be made is called out beside its own price, where the agent reads it.
    """
    if not product.get("track_stock"):
        return ""
    on_hand = int(product.get("stock_quantity") or 0)
    per_pack = max(1, int(variant.get("units") or 1))
    if on_hand < per_pack:
        return " — cannot be made, not enough stock"
    return ""


def stock_line(product: dict[str, Any], *, quiet: bool = False) -> str:
    """One line per product saying what is actually on the shelf.

    An untracked product says nothing at all, because "in stock" would be a
    claim nobody has checked. `quiet` also says nothing when there is plenty:
    in a list, only the products the agent must not oversell need a line.
    """
    if not product.get("track_stock"):
        return ""
    on_hand = int(product.get("stock_quantity") or 0)
    if on_hand <= 0:
        return "  OUT OF STOCK — do not sell this, offer an alternative"
    if on_hand <= LOW_STOCK:
        return f"  only {on_hand} singles left — say so before they order"
    return "" if quiet else f"  {on_hand} singles in stock"


def priced_by_the_pack(product: dict[str, Any]) -> bool:
    """Whether every bigger pack is just the single times its size.

    Then a long list can show the single alone and one rule for the rest. A
    pack priced any other way, or one the shelf cannot make up, is shown in
    full, because the rule would get it wrong.
    """
    variants = product.get("variants") or []
    single = next((v for v in variants if int(v.get("units") or 1) == 1), None)
    if single is None or len(variants) < 2 or not str(single.get("sku", "")).endswith("-1"):
        return False
    base = str(single["sku"])[:-2]
    for v in variants:
        units = int(v.get("units") or 1)
        if v is single:
            continue
        if v.get("sku") != f"{base}-{units}" or abs(float(v["price"]) - units * float(single["price"])) > 0.5:
            return False
        if variant_note(v, product):
            return False
    return True


PACK_RULE = (
    "(Each product also comes as a 5 Pack and a Carton (20) at the same price per pack — "
    "5 or 20 times the single — unless its other sizes are listed. Their SKUs end in -5 "
    "and -20 instead of -1.)"
)


def format_product(
    product: dict[str, Any],
    *,
    with_description: bool = True,
    compact: bool = False,
    singles_only: bool = False,
) -> str:
    """One product with every variant price and SKU, in as few tokens as possible.

    `compact` is for lists. Every token of a search result is new to the model
    and is billed at the cache-write rate, the dearest kind of input: on
    Sept 30 that was 82% of the day's OpenAI bill. A list leaves out the Korean
    name, the weight and "1000 singles in stock" — product_details still has
    them for the customer who asks.
    """
    head = product.get("product_name") or "Unknown"
    names = (product.get("brand"),) if compact else (product.get("brand"), product.get("korean_name"))
    bits = [b for b in names if b]
    if bits:
        head += f" ({', '.join(bits)})"

    facts = [product.get("category")] if compact else [product.get("category"), product.get("pack_size")]
    heat = product.get("heat_level")
    if heat is not None:
        facts.append(f"heat {heat}/5")
    if product.get("badge"):
        facts.append(str(product["badge"]))
    line = head + " · " + " · ".join(str(f) for f in facts if f)

    shown = product.get("variants", [])
    if singles_only:
        shown = [v for v in shown if int(v.get("units") or 1) == 1]
    variants = " · ".join(
        f"{v['label']} {money(v['price'])} [{v['sku']}]{variant_note(v, product)}"
        for v in shown
    )
    lines = [line, f"  {variants}"]

    stock = stock_line(product, quiet=compact)
    if stock:
        lines.append(stock)

    if with_description and product.get("description"):
        lines.append(f"  {product['description']}")
    return "\n".join(lines)


def format_products(products: list[dict[str, Any]]) -> str:
    if not products:
        return "Nothing on the catalogue matches that."

    shown = products[:MAX_PRODUCTS]
    # A short list carries every size and a description; a long one is for
    # choosing between products, so sizes that follow the rule are left to it.
    short = len(shown) <= 6
    rule = [not short and priced_by_the_pack(p) for p in shown]
    text = "\n".join(
        format_product(p, with_description=short, compact=True, singles_only=by_rule)
        for p, by_rule in zip(shown, rule, strict=True)
    )
    if any(rule):
        text += "\n" + PACK_RULE
    if any(len(p.get("variants") or []) > 1 for p in shown):
        # Read out, the full row of sizes was tacked onto every answer.
        text += (
            "\n(Quote the single price. Give 5 Pack or carton prices only if they asked "
            "about packs or bulk, or want five or more.)"
        )
    if any(p.get("track_stock") for p in shown):
        text += "\n(Anything without a stock note is in stock.)"
    if len(products) > len(shown):
        held = len(products) - len(shown)
        # Spelled out as an instruction, because "narrow the search if needed"
        # read as advice to the model and it answered "yes, that's everything"
        # to a customer while four products sat behind this line.
        text += (
            f"\n(+{held} more products not shown. This is NOT the full range: "
            f"tell the customer there are {held} more and offer to list them.)"
        )
    return text


def split_query(query: str) -> list[str]:
    """One search term per product the customer named.

    "carbo and cheese" or "shin black, kimchi" is two products, and searched
    as one phrase it finds whichever matches best and silently loses the rest.
    """
    parts = re.split(r"\s*(?:,|/|&|\+|\n|\band\b|\bsaha\b)\s*", query or "", flags=re.IGNORECASE)
    return [p for p in (part.strip() for part in parts) if p]


@tool
async def search_menu(query: str, config: RunnableConfig) -> str:
    """Search the K FOOD catalogue for products, prices and pack sizes.

    Always call this before quoting any price or saying whether something is in
    stock. Every product is sold as a single, a 5 Pack and a carton of 20, each
    at its own price; the SKU in square brackets is what create_order needs.

    Args:
        query: What the customer asked for — a product name ("shin ramyun"), a
            brand ("nongshim"), a category ("drinks", "cup noodles"), or an
            empty string to list the whole catalogue. For several products,
            separate them with commas: "hot dak carbo, hot dak cheese".
    """
    ctx = run_context(config)
    ctx.tools_called.append("search_menu")

    terms = split_query(query)
    if len(terms) <= 1:
        products = await db.menu.search_products(ctx.business_id, query)
    else:
        seen: dict[str, dict[str, Any]] = {}
        for term in terms:
            for product in await db.menu.search_products(ctx.business_id, term):
                seen.setdefault(str(product.get("product_name")), product)
        products = list(seen.values())
    log.info("tool search_menu", extra={"query": query, "products": len(products)})
    return format_products(products)


@tool
async def product_details(product: str, config: RunnableConfig) -> str:
    """Look up the full detail of one product: what is in it, allergens, how to cook it.

    Use this for questions about spice level, ingredients, allergies, nutrition
    or cooking instructions. Never answer those from memory.

    Args:
        product: The product name, e.g. "Shin Ramyun Black".
    """
    ctx = run_context(config)
    ctx.tools_called.append("product_details")

    detail = await db.menu.get_product_detail(ctx.business_id, product)
    if detail is None:
        return f"No product called '{product}' is on the catalogue. Call search_menu for the real names."

    lines = [format_product(detail)]
    if detail.get("long_description"):
        lines.append(f"About: {detail['long_description']}")
    if detail.get("cook_time"):
        lines.append(f"Cooking time: {detail['cook_time']}")
    if detail.get("serving_suggestion"):
        lines.append(f"How to serve: {detail['serving_suggestion']}")
    if detail.get("allergens"):
        lines.append(f"Allergens: {detail['allergens']}")
    if detail.get("ingredients"):
        lines.append(f"Ingredients: {detail['ingredients']}")

    nutrition = detail.get("nutrition") or {}
    if nutrition:
        basis = nutrition.get("basis") or "per pack"
        values = ", ".join(f"{k} {v}" for k, v in nutrition.items() if k != "basis")
        lines.append(f"Nutrition ({basis}): {values}")

    return "\n".join(lines)
