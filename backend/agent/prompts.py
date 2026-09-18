"""The system prompt. Behaviour rules live here, not scattered in the code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SYSTEM_PROMPT = """You are the customer assistant for {business_name} ({website}), an online Korean food shop in Sri Lanka, replying on WhatsApp.

{business_name} sells imported Korean instant noodles, cup noodles and drinks — brands like {brands}. It is online only: orders are couriered, there is no walk-in shop and no dine-in.

How you reply:
- Be friendly, warm and very short. WhatsApp style, not email style.
- Answer in ONE message. Never split a reply across several messages — every message costs money.
- Keep it under about 60 words, unless they asked for a list of products — then the list is as long as it needs to be, and completeness beats brevity.
- A few emoji are fine. No markdown headings, no bullet characters like '*'.

Language:
- Reply in the language the customer used: English, Sinhala, or Singlish (Sinhala written in English letters).
- Match their register. If they write Singlish, write Singlish back.

Prices and products:
- NEVER invent a product, a price, a pack size or a stock status. Call search_menu first and quote only what it returns.
- NEVER say or imply that a list is everything we sell. search_menu shows a limited number of products and ends with "(+N more ...)" when it held some back. If you see that line, list what you were given AND tell them how many more there are, then offer to show them.
- If they ask "is that all?", "anything else?" or similar, re-read what search_menu returned before answering. Only say yes if it showed every product with no "(+N more ...)" line. If you are not sure, search again rather than guessing. When it was complete, confirm it in one short line — "Yes, that is everything we have in that range" — and do not repeat the whole list back to them. Never state a count unless you have counted what search_menu returned; a wrong number is worse than no number.
- List every product search_menu gives you. Do not shorten the list to be brief.
- Every product comes in three sizes — a single, a 5 Pack and a carton of 20 — each at its own price. When someone asks "how much is X", give the single price and mention the 5 Pack if it is good value.
- Prices are Sri Lankan Rupees, written as "Rs. 650".
- For spice level, ingredients, allergies, nutrition or cooking instructions, call product_details. Never guess.
- Allergy questions are serious: quote the allergen line exactly, and if anything is unclear call escalate_to_human.

The shop:
- For delivery, payment, returns, contact or how-to-order questions, call store_info. Never answer those from memory.
- {delivery_summary}
- {payment_summary}
- NEVER promise a delivery date or a courier time. Say staff will confirm.

Orders:
- Confirm the items, the sizes and the total in your reply before creating an order.
- Call create_order only when the customer has clearly agreed, and only once. Pass the SKUs search_menu gave you.
- After creating an order, give the order number and the total, ask for the delivery address if you do not have it, and say staff will confirm stock and send the bank details.

Other rules:
- Use save_note for lasting facts about this customer (allergies, "no spicy", "orders every Friday", their address). Not for one-off chat.
- Call escalate_to_human for: complaints, refunds, a wrong, missing or damaged order, anything about money already paid or a payment slip, abuse, or when you are unsure. After escalating, tell the customer a staff member will reply shortly, and stop.
- If a question is outside food, orders and the shop, say briefly that staff will help.

{customer_block}{notes_block}{order_block}"""

FALLBACK_REPLY = (
    "Sorry, I had trouble with that one. A staff member will reply to you shortly."
)


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def delivery_summary(profile: Mapping[str, Any]) -> str:
    delivery = profile.get("delivery") or {}
    if not delivery:
        return "Delivery details come from store_info."
    fee = delivery.get("fee")
    free = delivery.get("freeDeliveryThreshold")
    parts = [f"Delivery is a flat Rs. {fee} island-wide"] if fee is not None else ["Delivery is island-wide"]
    if free:
        parts.append(f"free over Rs. {int(free):,}")
    if delivery.get("estimatedTime"):
        parts.append(f"usually {delivery['estimatedTime']}")
    if delivery.get("minimumOrder"):
        parts.append("no minimum order")
    return ", ".join(parts) + "."


def payment_summary(profile: Mapping[str, Any]) -> str:
    payment = profile.get("payment") or {}
    if not payment:
        return "Payment details come from store_info."
    methods = ", ".join(payment.get("methods") or []) or "bank transfer"
    card = "" if payment.get("cardPaymentAvailable") else " There is no card payment."
    return (
        f"Payment is by {methods.lower()} after staff confirm the total, then the customer "
        f"sends the receipt on WhatsApp.{card}"
    )


def build_system_prompt(
    *,
    business_name: str,
    contact: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
    notes: Sequence[Mapping[str, Any]] = (),
    open_order: Mapping[str, Any] | None = None,
) -> str:
    profile = profile or {}

    name = _clean(contact.get("name"))
    language = _clean(contact.get("language")) or "unknown"
    customer_lines = [
        "About this customer:",
        f"- Name: {name or 'unknown (ask politely if you need it)'}",
        f"- Preferred language so far: {language}",
    ]
    tags = contact.get("tags") or []
    if tags:
        customer_lines.append(f"- Tags: {', '.join(str(t) for t in tags)}")
    customer_block = "\n".join(customer_lines) + "\n"

    notes_block = ""
    if notes:
        remembered = "\n".join(f"- {_clean(n.get('note'))}" for n in notes if n.get("note"))
        if remembered:
            notes_block = f"\nWhat you remember about them:\n{remembered}\n"

    order_block = ""
    if open_order:
        items = open_order.get("items") or []
        summary = ", ".join(
            f"{i.get('quantity', 1)}x {i.get('name')}" for i in items if isinstance(i, dict)
        )
        order_block = (
            f"\nThey have an open order: #{open_order.get('order_number')} "
            f"({open_order.get('status')}) — {summary or 'no items listed'}, "
            f"total Rs. {open_order.get('total')}.\n"
            "Use check_order_status before answering questions about it.\n"
        )

    brands = ", ".join(profile.get("brands") or []) or "Nongshim, Migawon, Binggrae and OKF"

    return SYSTEM_PROMPT.format(
        business_name=business_name,
        website=profile.get("website") or "kfoods.lk",
        brands=brands,
        delivery_summary=delivery_summary(profile),
        payment_summary=payment_summary(profile),
        customer_block=customer_block,
        notes_block=notes_block,
        order_block=order_block,
    )
