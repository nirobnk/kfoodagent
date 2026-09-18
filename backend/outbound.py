"""Outbound message policy: window check, template fallback, logging.

Every message this system sends to a customer goes through here — agent
replies, staff replies typed in the dashboard, and order status notifications.
That is what guarantees the 24-hour window is checked exactly once per send and
that every send is written to the `messages` table.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import db
from whatsapp import WhatsAppError, can_send_free_text, get_client

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SendResult:
    ok: bool
    wa_message_id: str | None = None
    template_name: str | None = None
    reason: str | None = None

    @property
    def used_template(self) -> bool:
        return self.template_name is not None


async def send_text(
    *,
    business_id: str,
    contact: Mapping[str, Any],
    body: str,
    sender: str = "agent",
    force: bool = False,
) -> SendResult:
    """Send free-form text if the 24-hour window is open.

    Outside the window Meta rejects free text, so we refuse before spending the
    call and tell the caller to use a template instead.
    """
    body = (body or "").strip()
    if not body:
        return SendResult(ok=False, reason="empty_body")

    if not force and not can_send_free_text(contact):
        log.warning(
            "free text blocked: 24h window closed",
            extra={"wa_id": contact.get("wa_id"), "contact_id": contact.get("id")},
        )
        return SendResult(ok=False, reason="window_closed")

    client = get_client()
    try:
        wa_message_id = await client.send_text(contact["wa_id"], body)
    except WhatsAppError as exc:
        await db.messages.save(
            business_id=business_id,
            contact_id=contact["id"],
            direction="out",
            sender=sender,
            body=body,
            status="failed",
            error=str(exc)[:500],
        )
        return SendResult(ok=False, reason=f"send_failed:{exc.code or 'unknown'}")

    await db.messages.save(
        business_id=business_id,
        contact_id=contact["id"],
        direction="out",
        sender=sender,
        body=body,
        wa_message_id=wa_message_id or None,
        status="sent",
    )
    return SendResult(ok=True, wa_message_id=wa_message_id)


async def send_image(
    *,
    business_id: str,
    contact: Mapping[str, Any],
    image_url: str,
    caption: str = "",
    sender: str = "agent",
) -> SendResult:
    """Send one product photo, subject to the same window rule as free text.

    An image is a message like any other: it costs money, it is blocked outside
    the 24-hour window, and it belongs in the `messages` table so the dashboard
    shows staff what the customer was actually sent.
    """
    image_url = (image_url or "").strip()
    if not image_url:
        return SendResult(ok=False, reason="no_image")

    if not can_send_free_text(contact):
        log.warning(
            "image blocked: 24h window closed",
            extra={"wa_id": contact.get("wa_id"), "contact_id": contact.get("id")},
        )
        return SendResult(ok=False, reason="window_closed")

    # The dashboard renders media_url as the image and shows this underneath,
    # so the body is the caption alone. "[photo]" only stands in when a photo
    # carried no caption, so a chat-list preview still reads as something.
    body = caption.strip() or "[photo]"

    client = get_client()
    try:
        wa_message_id = await client.send_image(contact["wa_id"], image_url, caption=caption)
    except WhatsAppError as exc:
        await db.messages.save(
            business_id=business_id,
            contact_id=contact["id"],
            direction="out",
            sender=sender,
            body=body,
            media_url=image_url,
            message_type="image",
            status="failed",
            error=str(exc)[:500],
        )
        return SendResult(ok=False, reason=f"send_failed:{exc.code or 'unknown'}")

    await db.messages.save(
        business_id=business_id,
        contact_id=contact["id"],
        direction="out",
        sender=sender,
        body=body,
        media_url=image_url,
        message_type="image",
        wa_message_id=wa_message_id or None,
        status="sent",
    )
    return SendResult(ok=True, wa_message_id=wa_message_id)


async def send_template(
    *,
    business_id: str,
    contact: Mapping[str, Any],
    key: str,
    variables: Iterable[Any] = (),
    body_preview: str | None = None,
    sender: str = "agent",
) -> SendResult:
    """Send a pre-approved template. Legal inside and outside the window."""
    template = await db.templates.get_approved(business_id, key)
    if template is None:
        return SendResult(ok=False, reason="template_unavailable")

    variables = list(variables)
    expected = len(template.get("variables") or [])
    if expected and len(variables) != expected:
        log.error(
            "template variable count mismatch",
            extra={"key": key, "expected": expected, "given": len(variables)},
        )
        return SendResult(ok=False, reason="template_variable_mismatch")

    client = get_client()
    try:
        wa_message_id = await client.send_template(
            contact["wa_id"],
            template["name"],
            language=template.get("language") or "en",
            variables=variables,
        )
    except WhatsAppError as exc:
        await db.messages.save(
            business_id=business_id,
            contact_id=contact["id"],
            direction="out",
            sender=sender,
            body=body_preview or _render_preview(template, variables),
            message_type="template",
            template_name=template["name"],
            status="failed",
            error=str(exc)[:500],
        )
        return SendResult(ok=False, reason=f"send_failed:{exc.code or 'unknown'}")

    await db.messages.save(
        business_id=business_id,
        contact_id=contact["id"],
        direction="out",
        sender=sender,
        body=body_preview or _render_preview(template, variables),
        message_type="template",
        template_name=template["name"],
        wa_message_id=wa_message_id or None,
        status="sent",
    )
    return SendResult(ok=True, wa_message_id=wa_message_id, template_name=template["name"])


async def send_with_fallback(
    *,
    business_id: str,
    contact: Mapping[str, Any],
    body: str,
    template_key: str | None = None,
    variables: Iterable[Any] = (),
    sender: str = "agent",
) -> SendResult:
    """Free text inside the window, the matching template outside it."""
    if can_send_free_text(contact):
        return await send_text(
            business_id=business_id, contact=contact, body=body, sender=sender
        )

    if template_key is None:
        return SendResult(ok=False, reason="window_closed")

    # Log what the customer actually received: the hydrated template, not the
    # free-text version we could not send.
    return await send_template(
        business_id=business_id,
        contact=contact,
        key=template_key,
        variables=variables,
        sender=sender,
    )


# ---------------------------------------------------------------------------
# Order status notifications (plan.md Phase 4)
# ---------------------------------------------------------------------------

def order_status_text(status: str, order: Mapping[str, Any]) -> str | None:
    number = order.get("order_number")
    total = order.get("total")
    try:
        total_text = f"{float(total):,.0f}" if total is not None else "0"
    except (TypeError, ValueError):
        total_text = str(total)

    return {
        "confirmed": f"Order #{number} confirmed. Total Rs. {total_text}.",
        "preparing": f"We are preparing order #{number}.",
        "dispatched": f"Order #{number} is on the way.",
        "delivered": f"Order #{number} delivered. Thank you!",
        "cancelled": f"Order #{number} has been cancelled. Message us if this is wrong.",
    }.get(status)


def order_status_template(status: str) -> str | None:
    return {
        "confirmed": "order_confirmed",
        "dispatched": "order_dispatched",
        "delivered": "order_delivered",
    }.get(status)


def order_template_variables(
    status: str, order: Mapping[str, Any], contact: Mapping[str, Any]
) -> list[Any]:
    name = contact.get("name") or "there"
    number = order.get("order_number")
    total = order.get("total")
    total_text = f"{float(total or 0):,.0f}"
    if status == "confirmed":
        return [name, number, total_text]
    if status == "dispatched":
        return [name, number]
    if status == "delivered":
        return [number]
    return []


async def notify_order_status(
    *, business_id: str, order: Mapping[str, Any], contact: Mapping[str, Any], status: str
) -> SendResult:
    body = order_status_text(status, order)
    if body is None:
        return SendResult(ok=False, reason="no_message_for_status")

    return await send_with_fallback(
        business_id=business_id,
        contact=contact,
        body=body,
        template_key=order_status_template(status),
        variables=order_template_variables(status, order, contact),
        sender="system",
    )


def _render_preview(template: Mapping[str, Any], variables: list[Any]) -> str:
    preview = template.get("body_preview") or template.get("name") or ""
    for index, value in enumerate(variables, start=1):
        preview = preview.replace(f"{{{{{index}}}}}", str(value))
    return preview
