"""Outbound message policy: window check, template fallback, logging.

Every message this system sends to a customer goes through here — agent
replies, staff replies typed in the dashboard, and order status notifications.
That is what guarantees the 24-hour window is checked exactly once per send and
that every send is written to the `messages` table.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from PIL import Image

import db
from whatsapp import WhatsAppError, can_send_free_text, get_client

log = logging.getLogger(__name__)

# WhatsApp accepts only JPEG and PNG for an image message; a .webp link comes
# back as "Media upload error". Shin Ramyun Original and Shin Ramyun Cup are
# webp in the catalogue, so they are converted to JPEG, uploaded, and sent by
# media id instead of being reported to the customer as having no photo.
LINKABLE_SUFFIXES = (".jpg", ".jpeg", ".png")
MAX_SOURCE_IMAGE_BYTES = 5 * 1024 * 1024
# Meta keeps an uploaded file for 30 days. Reuse the id well inside that, so a
# popular product is converted and uploaded once, not on every request.
UPLOAD_REUSE_SECONDS = 20 * 24 * 3600
_uploaded: dict[str, tuple[str, float]] = {}


def is_linkable_image(image_url: str) -> bool:
    path = image_url.split("?", 1)[0].split("#", 1)[0].lower()
    return path.endswith(LINKABLE_SUFFIXES)


def _to_jpeg(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
        else:
            flat = image.convert("RGB")
    out = io.BytesIO()
    flat.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue()


async def _fetch_image(image_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
        response = await http.get(image_url)
        response.raise_for_status()
    if len(response.content) > MAX_SOURCE_IMAGE_BYTES:
        raise ValueError(f"source image is larger than {MAX_SOURCE_IMAGE_BYTES} bytes")
    return response.content


async def _uploaded_jpeg_id(image_url: str, client: Any) -> str:
    """Fetch an image Meta will not take by link, and upload it as a JPEG."""
    cached = _uploaded.get(image_url)
    if cached and time.monotonic() - cached[1] < UPLOAD_REUSE_SECONDS:
        return cached[0]

    jpeg = await asyncio.to_thread(_to_jpeg, await _fetch_image(image_url))
    name = image_url.split("?", 1)[0].rsplit("/", 1)[-1].rsplit(".", 1)[0] or "photo"
    media_id = await client.upload_media(jpeg, "image/jpeg", f"{name}.jpg")
    _uploaded[image_url] = (media_id, time.monotonic())
    return media_id


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
    media_id: str | None = None
    try:
        if not is_linkable_image(image_url):
            try:
                media_id = await _uploaded_jpeg_id(image_url, client)
            except WhatsAppError:
                raise
            except Exception as exc:
                raise WhatsAppError(f"could not convert image: {type(exc).__name__}: {exc}") from exc
        wa_message_id = await client.send_image(
            contact["wa_id"], image_url, caption=caption, media_id=media_id
        )
    except WhatsAppError as exc:
        if media_id:
            # The upload may have expired early; the next send uploads afresh.
            _uploaded.pop(image_url, None)
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
