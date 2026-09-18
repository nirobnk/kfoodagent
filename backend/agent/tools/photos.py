"""Send a product photo into the chat.

Customers ask to see what they are buying — "photos ewanna puluwanda" — and
before this the agent could only point them at the website, which is a worse
answer than the catalogue could already support: most products carry an
image_url, and WhatsApp sends images by URL with no upload step.
"""

from __future__ import annotations

import logging
import re

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
import outbound
from agent.state import run_context

log = logging.getLogger(__name__)

# Each photo is a separate WhatsApp message and every message costs money, so a
# request like "show me the drinks" sends a taste, not the whole shelf.
MAX_PHOTOS = 3

# Words that carry no identity, so their absence should not reject a match.
_FILLER = {"the", "and", "pack", "flavour", "flavoured", "flavor", "drink", "cup"}


def _is_the_product_asked_for(requested: str, product: dict) -> bool:
    """Guard against the catalogue's deliberately fuzzy name lookup.

    get_product_detail falls back to a broad search and returns the first hit,
    which is right when answering a question — "banana milk" should find the
    Binggrae — but wrong for a photo: asking for "Unicorn Ramyun" matched Shin
    Ramyun Original, and a customer could order from that picture. A photo has
    to be of the thing they named, so every distinctive word they used must
    appear somewhere in the product's own names.
    """
    haystack = " ".join(
        str(product.get(field) or "")
        for field in ("product_name", "brand", "korean_name", "category", "handle")
    ).lower()
    words = [w for w in re.split(r"[^a-z0-9]+", requested.lower()) if len(w) > 2]
    significant = [w for w in words if w not in _FILLER]
    if not significant:
        return False
    return all(word in haystack for word in significant)


@tool
async def send_product_photo(products: str, config: RunnableConfig) -> str:
    """Send the customer a photo of one or more products, in the chat.

    Use this when they ask to see a product — "photo", "pic", "photos ewanna
    puluwanda", "how does it look". Do not promise a photo without calling this,
    and do not send customers to the website when this can show them directly.

    At most 3 photos go out per call, because each one is a paid message. Not
    every product has a photo; the reply tells you which ones were sent and
    which have none, so you can say so honestly.

    Args:
        products: The product names to show, comma separated, exactly as
            search_menu spelled them — e.g. "Binggrae Banana Flavoured Milk" or
            "Shin Ramyun Black, Kimchi Ramyun".
    """
    ctx = run_context(config)
    ctx.tools_called.append("send_product_photo")

    names = [n.strip() for n in (products or "").split(",") if n.strip()]
    if not names:
        return "No product named. Call search_menu first, then pass the exact names."

    sent: list[str] = []
    missing: list[str] = []
    unknown: list[str] = []
    failed: list[str] = []

    for name in names:
        if len(sent) >= MAX_PHOTOS:
            break

        product = await db.menu.get_product_detail(ctx.business_id, name)
        if product is None or not _is_the_product_asked_for(name, product):
            unknown.append(name)
            continue

        image_url = (product.get("image_url") or "").strip()
        label = product.get("product_name") or name
        if not image_url:
            missing.append(label)
            continue

        result = await outbound.send_image(
            business_id=ctx.business_id,
            contact=ctx.contact,
            image_url=image_url,
            caption=label,
        )
        if result.ok:
            sent.append(label)
        else:
            failed.append(label)
            log.warning(
                "product photo failed",
                extra={"product": label, "reason": result.reason},
            )

    ctx.photos_sent.extend(sent)
    log.info(
        "tool send_product_photo",
        extra={"sent": len(sent), "missing": len(missing), "unknown": len(unknown)},
    )

    # The model has to describe what really happened, so spell it out rather
    # than returning a bare "ok" it would have to guess the meaning of.
    lines: list[str] = []
    if sent:
        lines.append(f"Photo sent for: {', '.join(sent)}. Do not describe it, they can see it.")
    if missing:
        lines.append(f"No photo on file for: {', '.join(missing)}. Tell the customer honestly.")
    if unknown:
        lines.append(f"Not on the catalogue: {', '.join(unknown)}. Check the name with search_menu.")
    if failed:
        lines.append(f"Sending failed for: {', '.join(failed)}. Apologise and offer the website.")
    if not lines:
        return "Nothing was sent."
    return " ".join(lines)
