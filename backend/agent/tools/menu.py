"""Catalogue lookup. The only way the agent learns a price."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)

MAX_PRODUCTS = 12


def money(value: Any) -> str:
    try:
        return f"Rs. {float(value):,.0f}"
    except (TypeError, ValueError):
        return f"Rs. {value}"


def format_product(product: dict[str, Any], *, with_description: bool = True) -> str:
    """One product with every variant price and SKU, in as few tokens as possible."""
    head = product.get("product_name") or "Unknown"
    bits = [b for b in (product.get("brand"), product.get("korean_name")) if b]
    if bits:
        head += f" ({', '.join(bits)})"

    facts = [product.get("category"), product.get("pack_size")]
    heat = product.get("heat_level")
    if heat is not None:
        facts.append(f"heat {heat}/5")
    if product.get("badge"):
        facts.append(str(product["badge"]))
    line = head + " · " + " · ".join(str(f) for f in facts if f)

    variants = " · ".join(
        f"{v['label']} {money(v['price'])} [{v['sku']}]" for v in product.get("variants", [])
    )
    lines = [line, f"  {variants}"]

    if with_description and product.get("description"):
        lines.append(f"  {product['description']}")
    return "\n".join(lines)


def format_products(products: list[dict[str, Any]]) -> str:
    if not products:
        return "Nothing on the catalogue matches that."

    shown = products[:MAX_PRODUCTS]
    text = "\n".join(format_product(p, with_description=len(shown) <= 6) for p in shown)
    if len(products) > len(shown):
        text += f"\n(+{len(products) - len(shown)} more products — narrow the search if needed.)"
    return text


@tool
async def search_menu(query: str, config: RunnableConfig) -> str:
    """Search the K FOOD catalogue for products, prices and pack sizes.

    Always call this before quoting any price or saying whether something is in
    stock. Every product is sold as a single, a 5 Pack and a carton of 20, each
    at its own price; the SKU in square brackets is what create_order needs.

    Args:
        query: What the customer asked for — a product name ("shin ramyun"), a
            brand ("nongshim"), a category ("drinks", "cup noodles"), or an
            empty string to list the whole catalogue.
    """
    ctx = run_context(config)
    ctx.tools_called.append("search_menu")

    products = await db.menu.search_products(ctx.business_id, query)
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
