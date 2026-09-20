"""Matching a customer to a pack, the way someone behind a counter would.

`search_menu` answers "what have you got" — it needs a word to look for, and
returns everything that matches it. It is no help at all with the commonest
opening message in this shop, which is some version of "I don't know, what's
good?". Answering that means starting from the customer instead of the
catalogue: how much heat they can take, whether they want soup or a stir fry,
whether it is a snack or dinner, what they are willing to spend.

So this tool takes a taste, not a search term. It scores every product against
what the customer said and returns a handful with the reason each one matched,
so the reply can say *why* — "this one's the mild end of the range" — rather
than reading out a list and leaving them exactly where they started.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context
from agent.tools.menu import money, stock_line

log = logging.getLogger(__name__)

# Three or four is a recommendation; ten is the catalogue again.
MAX_SUGGESTIONS = 4

# How far outside the band a product may still be offered. Someone who says
# "not too spicy" is better served by the mildest thing on the shelf, said
# honestly, than by "nothing fits" — but never by a 5/5.
MAX_HEAT_DRIFT = 2

# Heat as customers describe it, mapped onto the catalogue's 0-5 scale. The
# bands overlap because "medium" and "spicy" are not precise words and a
# customer who says either will happily eat a 3.
HEAT_BANDS: dict[str, tuple[int, int]] = {
    "none": (0, 0),
    "mild": (0, 2),
    "medium": (2, 3),
    "hot": (3, 4),
    "extreme": (4, 5),
}

# Longest phrase wins, which is what makes the negations work: "not too
# spicy" has to be read before the "spicy" inside it, or the customer who
# asked for mild gets sent the fire noodles.
HEAT_WORDS: dict[str, str] = {
    "not too spicy": "mild",
    "not very spicy": "mild",
    "not that spicy": "mild",
    "less spicy": "mild",
    "too spicy": "mild",
    "not spicy": "none",
    "no spice": "none",
    "no spicy": "none",
    "cannot eat spicy": "none",
    "can't eat spicy": "none",
    "sudu": "none",
    "mild": "mild",
    "slightly": "mild",
    "little spicy": "mild",
    "podi": "mild",
    "medium": "medium",
    "normal": "medium",
    "spicy": "hot",
    "hot": "hot",
    "sappa": "hot",
    "very spicy": "extreme",
    "extra spicy": "extreme",
    "super spicy": "extreme",
    "most spicy": "extreme",
    "spiciest": "extreme",
    "hottest": "extreme",
    "very hot": "extreme",
    "extra hot": "extreme",
    "super hot": "extreme",
    "fire": "extreme",
    "buldak": "extreme",
    "challenge": "extreme",
    "burn": "extreme",
}

# What a customer is in the mood for, and the catalogue words that mean it.
STYLE_WORDS: dict[str, tuple[str, ...]] = {
    "soup": ("soup", "broth", "stew", "kimchi", "seafood"),
    "stir fry": ("stir fry", "stir-fry", "sauce", "dry", "hot dak", "buldak"),
    "cup": ("cup", "oncup", "bowl"),
    "drink": ("beverage", "milk", "latte", "juice", "soda", "aloe", "energy"),
    "cheesy": ("cheese", "carbo", "creamy"),
    "sweet": ("sweet", "banana", "strawberry", "melon", "honey", "corn"),
}


# Words that say nothing about taste. Without this list "I want the hottest
# thing you have" scored a match on every product whose description happens to
# contain the word "the", and the best seller badge then carried a 4/5 above
# the 5/5 the customer had explicitly asked for.
STOPWORDS = frozenset(
    """the and but for you your our can have has want need would like some any
    one two get got give please thanks thank hello hii much many this that
    they them there here what when which how are was were will with without
    from into about also just only very too not don dont mata mage eka ekak
    ekata tikak puluwanda karanna thiyenawa thiyenwa oya mama""".split()
)


def _clean_words(text: str) -> list[str]:
    """The words in a sentence that actually carry a preference."""
    return [
        w
        for w in re.split(r"[^a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in STOPWORDS
    ]


def _mentions(haystack: str, word: str) -> bool:
    """Whole-word match, so "milk" does not match "milkshake"-style accidents
    and a two-letter fragment cannot match half the catalogue."""
    return re.search(rf"\b{re.escape(word)}", haystack) is not None


def infer_heat(taste: str) -> str | None:
    """Read a heat band out of whatever the customer actually wrote."""
    text = (taste or "").lower()
    # Longest phrase first, so "very spicy" does not get read as "spicy".
    for phrase in sorted(HEAT_WORDS, key=len, reverse=True):
        if phrase in text:
            return HEAT_WORDS[phrase]
    return None


def _haystack(product: dict[str, Any]) -> str:
    return " ".join(
        str(product.get(field) or "")
        for field in ("product_name", "brand", "korean_name", "category", "description", "handle")
    ).lower()


def _cheapest(product: dict[str, Any]) -> dict[str, Any] | None:
    variants = product.get("variants") or []
    return variants[0] if variants else None


def score(
    product: dict[str, Any],
    *,
    band: str | None,
    taste: str,
    max_price: float | None,
    avoid: list[str],
) -> tuple[float, list[str]]:
    """How well this product fits, and the reasons to say out loud.

    Reasons are the point. A score alone would give the model a ranked list it
    would then have to invent a justification for, which is how a mild noodle
    gets sold to someone as "perfect for your spice level".
    """
    haystack = _haystack(product)
    reasons: list[str] = []
    points = 0.0

    for word in avoid:
        if word and _mentions(haystack, word):
            return (-1.0, [])

    heat = product.get("heat_level")
    if band:
        low, high = HEAT_BANDS[band]
        if heat is None:
            # A drink has no heat level. It only belongs in a heat-led answer
            # when they asked for a drink.
            points -= 2.0
        else:
            level = int(heat)
            if low <= level <= high:
                # Inside the band is not the same as being what they meant.
                # "The hottest you have" and "spicy" both land in the top
                # band, and only one of them wants the 5/5.
                target = high if band in ("hot", "extreme") else low if band in ("none", "mild") else (low + high) // 2
                off = abs(level - target)
                points += 4.0 + (3.0 if off == 0 else max(0.0, 3.0 - 1.5 * off))
                # The model reads this reason out loud, so a 4/5 must not be
                # sold as the hottest thing in the shop just because it landed
                # inside the band.
                reasons.append(
                    f"heat {level}/5, right at the {band} end"
                    if off == 0
                    else f"heat {level}/5, inside the {band} range"
                )
            else:
                drift = low - level if level < low else level - high
                if drift > MAX_HEAT_DRIFT:
                    return (-1.0, [])
                points += 4.0 - 1.5 * drift
                direction = "hotter" if level > high else "milder"
                reasons.append(
                    f"heat {level}/5 — {direction} than they asked for, but the closest we have"
                )

    for style, words in STYLE_WORDS.items():
        if style in (taste or "").lower() or any(w in (taste or "").lower() for w in words):
            if any(w in haystack for w in words):
                points += 3.0
                reasons.append(f"matches the {style} they asked for")
                break

    overlap = [w for w in _clean_words(taste) if _mentions(haystack, w)]
    if overlap:
        points += min(len(overlap), 3) * 1.5
        reasons.append("matches what they described")

    cheapest = _cheapest(product)
    if max_price is not None and cheapest:
        if float(cheapest["price"]) <= max_price:
            points += 2.0
            reasons.append(f"a single is {money(cheapest['price'])}, inside their budget")
        else:
            return (-1.0, [])

    badge = (product.get("badge") or "").strip()
    if badge:
        # Worth mentioning, never worth more than the taste they described:
        # a "Best Seller" badge once pushed a 4/5 above the 5/5 someone had
        # asked for by name.
        points += 1.0
        reasons.append(badge.lower())

    if product.get("track_stock") and int(product.get("stock_quantity") or 0) <= 0:
        # Never recommend what cannot be sent today.
        return (-1.0, [])

    return (points, reasons)


def format_suggestion(product: dict[str, Any], reasons: list[str]) -> str:
    name = product.get("product_name") or "Unknown"
    brand = product.get("brand")
    head = f"{name} ({brand})" if brand else name

    variants = " · ".join(
        f"{v['label']} {money(v['price'])} [{v['sku']}]" for v in product.get("variants", [])
    )
    lines = [f"{head} — {variants}"]
    if reasons:
        lines.append(f"  why: {'; '.join(reasons[:3])}")
    if product.get("description"):
        lines.append(f"  {product['description']}")
    stock = stock_line(product)
    if stock:
        lines.append(stock)
    return "\n".join(lines)


@tool
async def suggest_products(
    config: RunnableConfig,
    taste: str,
    spice: str | None = None,
    max_price: float | None = None,
    avoid: str | None = None,
) -> str:
    """Pick the products that match a customer's taste, with the reason for each.

    Use this whenever someone is deciding rather than asking for a named
    product: "what do you recommend", "mata mokakda hodama", "something not
    too spicy", "first time trying Korean noodles", "a gift for my sister",
    "what goes with fire noodles". Also use it to follow up an order with one
    natural suggestion.

    If you do not yet know what they like, ask ONE short question first — how
    much spice they can take is usually the one that decides everything — then
    call this with their answer. Never guess a recommendation without calling
    this: the reasons it returns are what make the suggestion worth reading.

    Args:
        taste: What the customer said they want, in their own words — "soupy
            and not too hot", "spicy stir fry", "sweet drink for a kid".
        spice: How much heat they want, if you know: "none", "mild", "medium",
            "hot" or "extreme". Leave empty to read it out of `taste`.
        max_price: The most they want to spend on one pack, in rupees.
        avoid: Anything to keep out — an allergen, a brand, "no seafood".
    """
    ctx = run_context(config)
    ctx.tools_called.append("suggest_products")

    band = (spice or "").strip().lower() or None
    if band not in HEAT_BANDS:
        band = infer_heat(f"{spice or ''} {taste or ''}")

    avoid_words = _clean_words(avoid or "")
    products = await db.menu.search_products(ctx.business_id, "")

    ranked: list[tuple[float, list[str], dict[str, Any]]] = []
    for product in products:
        points, reasons = score(
            product, band=band, taste=taste or "", max_price=max_price, avoid=avoid_words
        )
        if points > 0:
            ranked.append((points, reasons, product))

    ranked.sort(key=lambda row: row[0], reverse=True)
    top = ranked[:MAX_SUGGESTIONS]

    log.info(
        "tool suggest_products",
        extra={"taste": taste, "band": band, "matched": len(ranked)},
    )

    if not top:
        return (
            "Nothing in the catalogue fits that. Say so plainly, ask one short question "
            "to narrow it down — spice level, soup or stir fry, noodles or a drink — and "
            "call search_menu to show them what there is."
        )

    body = "\n".join(format_suggestion(product, reasons) for _, reasons, product in top)
    return (
        f"{len(top)} good matches, best first:\n{body}\n"
        "Suggest two or three of these in your own words, each with the one reason it "
        "suits them, and ask which they would like. Quote only these prices and SKUs."
    )
