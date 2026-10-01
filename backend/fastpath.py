"""Replies that need no model: the ad opener and a bare "price?".

On Sept 30, 56 of 139 customer messages were the click-to-WhatsApp ad's
prefilled "Hi! I want to order Korean ramen 🍜" and 29 more were a bare price
question — "Price", "kiyada", "මිල ගනන්", "price list ewnna". Each cost a
model call, and the opener was answered with a question about spice instead
of prices, after which 26 customers never wrote again. Here they get the
price list straight away, in under a second, at no model cost.

Only a burst made entirely of these is answered here. "Hi! I want to order
Korean ramen" followed by "Shin Black price?" names a product, so it goes to
the agent, which reads both.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import db
from agent.tools.pricelist import build_price_list

# The ad's prefilled text, as it reads with punctuation and emoji stripped.
OPENERS = (
    "hi i want to order korean ramen",
    "hi how to order korean ramen",
)

# A message made only of these, with at least one PRICE_WORDS, is a bare
# price question. Product names are deliberately absent: "shin price" is not.
PRICE_WORDS = {
    "price", "prices", "pricelist", "parice", "pricelistekak", "menu", "rates",
    "kiyada", "kiyda", "kiyadha", "much",
    "කීයද", "මිල", "ගනන්", "ගණන්", "මිලගනන්",
}
FILLER = {
    "list", "eka", "ek", "ekak", "ewanna", "ewnna", "ewana", "evanna", "denna", "dnna",
    "please", "pls", "plz", "pl", "send", "me", "all", "the", "your", "and", "what", "is",
    "are", "how", "kohomada", "kohomds", "kohomda", "mata", "oyalage", "hi", "hello",
    "ane", "full", "item", "items", "එවන්න", "දාන්න", "කොහොමද", "මට", "ලිස්ට්", "එක",
    # The range as a whole, not a product: "how much a Korean ramen?"
    "a", "korean", "ramen", "noodles", "noodle", "ramyun",
}

SINGLISH = {"kiyada", "kiyda", "kiyadha", "eka", "ek", "ekak", "ewanna", "ewnna", "ewana",
            "evanna", "denna", "dnna", "kohomada", "kohomds", "kohomda", "mata", "ane"}

CLOSING = {
    "si": "ඔයාට මොනවද ඕනේ? 😊 Spicy කොච්චර කැමතිද කිව්වොත් මම හොඳ ඒවා දෙක තුනක් තෝරලා දෙන්නම් 🌶️",
    "singlish": "Mokakda ganna kamathi? 😊 Spicy level eka kiyannath puluwan, mama hoda ewa dekak thunak select karala dennam 🌶️",
    "en": "Which one would you like? 😊 Or tell me how spicy you like it and I'll pick two or three for you 🌶️",
}


@dataclass(slots=True)
class FastReply:
    text: str
    reason: str  # "ad_opener" or "price_question"


def normalise(text: str) -> str:
    """Lower case, letters and digits only — Sinhala vowel signs kept."""
    kept = [
        ch if unicodedata.category(ch)[0] in "LNM" else " "
        for ch in (text or "").lower()
    ]
    return " ".join("".join(kept).split())


def is_price_question(normalised: str) -> bool:
    words = normalised.split()
    return bool(words) and all(w in PRICE_WORDS or w in FILLER for w in words) and any(
        w in PRICE_WORDS for w in words
    )


def classify(texts: list[str]) -> str | None:
    """"ad_opener", "price_question", or None when the agent must answer."""
    if not texts:
        return None
    saw_opener = saw_price = False
    for text in texts:
        clean = normalise(text)
        opener = next((o for o in OPENERS if clean.startswith(o)), None)
        if opener is not None:
            saw_opener = True
            rest = clean[len(opener):].strip()
            if not rest:
                continue
            clean = rest   # "Hi! I want to order Korean ramen 🍜 කීයද"
        if is_price_question(clean):
            saw_price = True
            continue
        return None
    if saw_price:
        return "price_question"
    return "ad_opener" if saw_opener else None


def language(texts: list[str]) -> str:
    joined = " ".join(texts)
    if re.search(r"[඀-෿]", joined):
        return "si"
    if set(normalise(joined).split()) & SINGLISH:
        return "singlish"
    return "en"


async def fast_reply(business_id: str, texts: list[str]) -> FastReply | None:
    """The reply for a burst of messages, or None when the agent must answer.

    Never raises: a catalogue read that fails hands the message to the agent.
    """
    kind = classify(texts)
    if kind is None:
        return None
    try:
        rows = await db.menu.list_available(business_id)
        profile = await db.business.get_profile(business_id)
        name = await db.business.get_name(business_id)
    except Exception:
        return None
    products = db.menu.group_by_product(rows)
    if not products:
        return None

    # They came from a ramen ad, so the opener gets the noodles; a price
    # question gets everything, drinks included.
    section = "noodles" if kind == "ad_opener" else "all"
    block = build_price_list(products, profile, business_name=name, section=section)
    greeting = "Hi! 😊 Here are our Korean noodles:\n\n" if kind == "ad_opener" else ""
    return FastReply(text=f"{greeting}{block}\n\n{CLOSING[language(texts)]}", reason=kind)
