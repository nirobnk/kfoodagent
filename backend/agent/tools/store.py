"""Delivery, payment, returns — everything the customer asks that is not a product."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import db
from agent.state import run_context

log = logging.getLogger(__name__)

TOPICS = {
    "delivery": ("deliver", "delivery", "courier", "ship", "post", "district", "how long",
                 "days", "colombo", "kandy", "area", "send"),
    "payment": ("pay", "payment", "bank", "transfer", "card", "cod", "cash", "account", "slip",
                "receipt"),
    "returns": ("return", "refund", "damaged", "expired", "wrong", "broken", "replace"),
    "contact": ("phone", "number", "email", "contact", "facebook", "instagram", "tiktok",
                "website", "shop", "address"),
    "ordering": ("order", "how do i", "minimum", "checkout", "cart"),
}


def _match_topics(question: str) -> list[str]:
    text = (question or "").lower()
    return [topic for topic, words in TOPICS.items() if any(word in text for word in words)]


def _delivery(profile: dict) -> str:
    d = profile.get("delivery") or {}
    free = d.get("freeDeliveryThreshold")
    return (
        f"Delivery: {d.get('coverage', 'Sri Lanka')}. "
        f"Flat Rs. {d.get('fee')} courier"
        + (f", free on orders over Rs. {free:,}" if free else "")
        + f". Usually arrives in {d.get('estimatedTime')}. "
        f"Minimum order: {d.get('minimumOrder')}. "
        "Never promise a delivery date — say staff will confirm."
    )


def _payment(profile: dict) -> str:
    p = profile.get("payment") or {}
    bank = p.get("bankDetails") or {}
    return (
        f"Payment: {', '.join(p.get('methods', []))} only — there is no card payment. "
        f"Bank: {bank.get('bank')}, {bank.get('branch')} branch. "
        f"Account name: {bank.get('accountName')}. Account number: {bank.get('accountNumber')}. "
        f"Process: {p.get('process')}"
    )


def _returns(profile: dict) -> str:
    r = profile.get("returns") or {}
    return (
        f"Returns: within {r.get('window')}. {r.get('process')} {r.get('conditions')}"
    )


def _contact(profile: dict) -> str:
    c = profile.get("contact") or {}
    whatsapp = (c.get("whatsapp") or {}).get("displayNumber")
    email = (c.get("email") or {}).get("address")
    social = c.get("social") or {}
    return (
        f"Contact: WhatsApp {whatsapp}, email {email}, website {profile.get('website')}. "
        f"Social: {', '.join(f'{k} {v}' for k, v in social.items())}. "
        f"{profile.get('trading_name')} is an online store — there is no walk-in shop."
    )


def _ordering(profile: dict) -> str:
    steps = profile.get("how_to_order") or []
    return "How to order: " + " ".join(f"{s['step']}. {s['title']} — {s['text']}" for s in steps)


BUILDERS = {
    "delivery": _delivery,
    "payment": _payment,
    "returns": _returns,
    "contact": _contact,
    "ordering": _ordering,
}


@tool
async def store_info(question: str, config: RunnableConfig) -> str:
    """Answer a question about the shop itself: delivery, payment, returns, contact, how to order.

    Use this for anything that is not about a specific product — "do you deliver
    to Jaffna?", "how do I pay?", "what if it arrives damaged?", "is there a
    shop I can visit?". Never answer these from memory: the facts are here.

    Args:
        question: The customer's question, in their own words.
    """
    ctx = run_context(config)
    ctx.tools_called.append("store_info")

    profile = await db.business.get_profile(ctx.business_id)
    if not profile:
        return "The store profile is not loaded. Escalate to a human."

    topics = _match_topics(question)
    parts = [BUILDERS[topic](profile) for topic in topics if topic in BUILDERS]

    faqs = await db.faqs.search(ctx.business_id, question, limit=2)
    for faq in faqs:
        parts.append(f"FAQ — {faq['question']} {faq['answer']}")

    if not parts:
        parts = [_delivery(profile), _payment(profile)]

    log.info("tool store_info", extra={"question": question, "topics": topics})
    return "\n".join(parts)
