"""Deterministic catalogue-wide dietary filtering.

Product recommendation is fuzzy; dietary exclusion cannot be. This tool reads
the full ingredient and allergen label for every candidate and reports either
eligible label matches or one final no-match result. It never turns an absence
of a listed ingredient into a vegetarian or vegan certification.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context
from agent.tools.menu import money

DIETARY_GROUPS: dict[str, tuple[str, ...]] = {
    "meat": ("beef", "ox", "chicken", "pork", "meat", "gelatin", "gelatine"),
    "seafood": (
        "fish",
        "anchovy",
        "shrimp",
        "prawn",
        "crab",
        "cuttlefish",
        "squid",
        "mussel",
        "shellfish",
    ),
    "egg": ("egg",),
    "dairy": ("milk", "cheese", "whey", "cream", "butter", "lactose"),
    "other animal products": ("royal jelly", "honey"),
}

GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "meat": ("meat", "non veg", "non-veg", "beef", "chicken", "pork"),
    "seafood": ("seafood", "fish", "shellfish", "prawn", "shrimp", "crab"),
    "egg": ("egg", "eggs"),
    "dairy": ("dairy", "milk", "cheese", "lactose"),
}


def _contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text) is not None


def _requirements(avoid: str) -> list[str]:
    text = (avoid or "").lower()
    wanted: list[str] = []

    if any(phrase in text for phrase in ("pure veg", "pure vegetarian", "vegetarian")):
        wanted.extend(("meat", "seafood", "egg"))
    if "vegan" in text or "all animal" in text:
        wanted.extend(DIETARY_GROUPS)

    for group, aliases in GROUP_ALIASES.items():
        if any(_contains(text, alias) for alias in aliases):
            wanted.append(group)

    return list(dict.fromkeys(wanted))


def _category_matches(product: dict[str, Any], category: str | None) -> bool:
    requested = (category or "").strip().lower()
    if not requested:
        return True
    actual = str(product.get("category") or "").lower()
    if requested in {"noodle", "noodles", "ramen", "ramyun"}:
        return "noodle" in actual
    if requested in {"drink", "drinks", "beverage", "beverages"}:
        return "beverage" in actual
    return requested in actual


def _hits(product: dict[str, Any], requirements: list[str], strict_traces: bool) -> list[str]:
    ingredients = str(product.get("ingredients") or "").lower()
    allergens = str(product.get("allergens") or "").lower()
    declared, separator, traces = allergens.partition("may contain")
    checked = f"{ingredients} {declared}"
    if strict_traces and separator:
        checked += f" {traces}"

    found: list[str] = []
    for group in requirements:
        terms = DIETARY_GROUPS[group]
        matched = [term for term in terms if _contains(checked, term)]
        if matched:
            found.append(f"{group} ({', '.join(matched)})")
    return found


def _price(product: dict[str, Any]) -> str:
    variants = product.get("variants") or []
    return money(variants[0].get("price")) if variants else "price unavailable"


@tool
async def find_dietary_options(
    config: RunnableConfig,
    avoid: str,
    category: str | None = None,
    strict_traces: bool = True,
) -> str:
    """Find products whose full labels meet dietary exclusions.

    Use this for vegetarian, vegan, pure-veg, no-meat, no-seafood, no-egg or
    similar catalogue-wide questions. Unlike search_menu and suggest_products,
    this reads ingredients and allergens for every candidate.

    Args:
        avoid: Everything the customer avoids, e.g. "meat, seafood and egg" or
            "vegan / all animal products".
        category: Optional scope such as "noodles" or "drinks".
        strict_traces: True when a label saying "may contain" also disqualifies
            the product. Ask this at most once if the customer has not said.
    """
    ctx = run_context(config)
    ctx.tools_called.append("find_dietary_options")

    requirements = _requirements(avoid)
    if not requirements:
        return (
            "DIETARY CHECK NEEDS ONE CLARIFICATION: name what must be avoided "
            "(for example meat, seafood, egg or dairy). Ask only that question."
        )

    products = [
        product
        for product in await db.menu.list_detailed_products(ctx.business_id)
        if _category_matches(product, category)
    ]
    checked = [(product, _hits(product, requirements, strict_traces)) for product in products]
    matches = [product for product, hits in checked if not hits]

    scope = category or "all products"
    rules = ", ".join(requirements)
    trace_rule = "including 'may contain' traces" if strict_traces else "direct ingredients only"

    if not matches:
        closest = sorted(
            ((product, hits) for product, hits in checked),
            key=lambda row: (len(row[1]), str(row[0].get("product_name") or "")),
        )[:2]
        lines = [
            "DIETARY CHECK: NO MATCH — FINAL ANSWER.",
            f"Scope: {scope}. Excluding: {rules}; {trace_rule}.",
            "Say once that the current catalogue has no confirmed match. Do not ask another "
            "taste question, repeat the search, or recommend an excluded product as safe.",
        ]
        if closest:
            lines.append("Examples that are not eligible:")
            for product, hits in closest:
                lines.append(
                    f"- {product.get('product_name')} — excluded by {', '.join(hits)}. "
                    f"Exact allergen line: {product.get('allergens') or 'not provided'}"
                )
        return "\n".join(lines)

    lines = [
        f"DIETARY CHECK: {len(matches)} label-based match(es) for {scope}.",
        f"Excluded: {rules}; {trace_rule}.",
        "These are matches against the recorded label, not vegetarian/vegan certification. "
        "Say that distinction plainly and quote each allergen line exactly.",
    ]
    for product in matches:
        lines.append(
            f"- {product.get('product_name')} — {_price(product)}. "
            f"Allergens: {product.get('allergens') or 'No allergen line recorded.'}"
        )
    return "\n".join(lines)
