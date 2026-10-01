"""The whole price list, laid out for a phone screen.

Typed out by the model, the list came back as twenty plain lines in shelf
order, different every time, and cut at twenty products — so the ten Oncup,
Olatte and Bacchus drinks were never on it. Built here, it is grouped, marked
for heat, complete, and the same for every customer.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context
from agent.tools.menu import money, priced_by_the_pack

log = logging.getLogger(__name__)

# (emoji, heading, which products belong). Checked in order; the first match wins.
GROUPS: list[tuple[str, str, Any]] = [
    ("🍜", "Shin Ramyun", lambda p: _name(p).startswith("shin ramyun") and _cat(p) == "instant noodles"),
    ("🔥", "Hot Dak Fire Noodles", lambda p: _name(p).startswith("hot dak")),
    ("🍲", "More Korean Noodles", lambda p: _cat(p) == "instant noodles"),
    ("🥡", "Cup Noodles", lambda p: _cat(p) == "cup noodles"),
    ("🥤", "Korean Drinks", lambda p: _cat(p) == "beverages"),
]
OTHER = ("🛒", "More from K FOOD")

SECTIONS = {
    "noodles": {"Shin Ramyun", "Hot Dak Fire Noodles", "More Korean Noodles", "Cup Noodles"},
    "drinks": {"Korean Drinks"},
}

POPULAR_BADGES = {"best seller", "korean icon"}
NEW_BADGES = {"new"}


def _name(product: dict[str, Any]) -> str:
    return str(product.get("product_name") or "").lower()


def _cat(product: dict[str, Any]) -> str:
    return str(product.get("category") or "").lower()


def heat_marks(heat: Any) -> str:
    """Three marks at most, so a line still fits on a phone."""
    if heat is None:
        return ""
    level = int(heat)
    if level <= 0:
        return " (no spice)"
    if level >= 5:
        return " 🔥🔥🔥"
    return " " + "🌶️" * {1: 1, 2: 1, 3: 2, 4: 3}[level]


def product_line(product: dict[str, Any]) -> tuple[str, set[str]]:
    """One product, and which legend marks it used."""
    single = next(
        (v for v in product.get("variants") or [] if int(v.get("units") or 1) == 1),
        (product.get("variants") or [{}])[0],
    )
    price = money(single.get("price", 0))
    name = product.get("product_name") or "Unknown"
    used: set[str] = set()

    out_of_stock = product.get("track_stock") and int(product.get("stock_quantity") or 0) <= 0
    if out_of_stock:
        return f"• {name} — ~{price}~ ❌ out of stock", used

    line = f"• {name} — *{price}*"
    heat = heat_marks(product.get("heat_level"))
    if "🔥" in heat:
        used.add("fire")
    elif heat.strip() and not heat.startswith(" ("):
        used.add("heat")
    line += heat
    badge = str(product.get("badge") or "").lower()
    if badge in POPULAR_BADGES:
        line += " ⭐"
        used.add("popular")
    elif badge in NEW_BADGES:
        line += " 🆕"
        used.add("new")
    return line, used


def build_price_list(
    products: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    business_name: str = "K FOOD",
    section: str = "all",
) -> str:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for product in products:
        group = next(((e, h) for e, h, belongs in GROUPS if belongs(product)), OTHER)
        if section in SECTIONS and group[1] not in SECTIONS[section]:
            continue
        grouped.setdefault(group, []).append(product)

    order = [(e, h) for e, h, _ in GROUPS] + [OTHER]
    blocks = [f"🇰🇷 *{business_name} Price List* 🍜"]
    used: set[str] = set()
    for group in order:
        if group not in grouped:
            continue
        lines = [f"{group[0]} *{group[1]}*"]
        for product in grouped[group]:
            line, marks = product_line(product)
            lines.append(line)
            used |= marks
        blocks.append("\n".join(lines))

    footer: list[str] = []
    legend = [
        text for key, text in (
            ("heat", "🌶️ spice level"), ("fire", "🔥 extra hot"),
            ("popular", "⭐ customer favourite"), ("new", "🆕 new"),
        ) if key in used
    ]
    if legend:
        footer.append(" · ".join(legend))
    shown = [p for g in grouped.values() for p in g]
    if shown and all(priced_by_the_pack(p) for p in shown):
        footer.append("📦 5 Pack = 5 × price · Carton (20) = 20 × price")
    else:
        footer.append("📦 5 Packs and cartons of 20 too — just ask")
    delivery = profile.get("delivery") or {}
    if delivery.get("fee") is not None:
        free = delivery.get("freeDeliveryThreshold")
        footer.append(
            f"🚚 Island-wide delivery Rs. {int(float(delivery['fee'])):,}"
            + (f" · *FREE* over Rs. {int(float(free)):,}" if free else "")
        )
    blocks.append("\n".join(footer))
    return "\n\n".join(blocks)


@tool
async def price_list(
    config: RunnableConfig,
    section: Literal["all", "noodles", "drinks"] = "all",
) -> str:
    """The full price list, ready to send.

    Use this whenever someone asks for the price list, the menu, "all prices",
    "what do you have", or asks "price?" / "kiyada?" without naming a product.
    For the price of one named product, use search_menu instead.

    Args:
        section: "noodles" or "drinks" if they asked about only one of them;
            otherwise "all".
    """
    ctx = run_context(config)
    ctx.tools_called.append("price_list")

    rows = await db.menu.list_available(ctx.business_id)
    products = db.menu.group_by_product(rows)
    profile = await db.business.get_profile(ctx.business_id)
    name = await db.business.get_name(ctx.business_id)
    block = build_price_list(products, profile, business_name=name, section=section)
    log.info("tool price_list", extra={"section": section, "products": len(products)})
    return (
        "Send the price list below EXACTLY as it is laid out — every line, the emojis, "
        "the *bold* and the blank lines — as your reply. Do not retype it as plain lines, "
        "reorder it, translate it, shorten it or add products. Then add ONE short line "
        "after it, in the customer's language, asking what they would like.\n\n"
        f"{block}"
    )
