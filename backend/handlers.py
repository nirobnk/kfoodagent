"""What happens to a message after the webhook has answered 200.

Order of operations for an inbound message — this order matters:
  1. idempotency check   (Meta retries; we must not answer twice)
  2. contact upsert
  3. persist the message
  4. touch the 24-hour window
  5. human_takeover check (the agent stays silent while staff are handling it)
  6. run the agent
  7. send exactly one reply
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

import db
import outbound
from agent import run_agent
from config import settings
from whatsapp import InboundMessage, StatusUpdate, get_client

log = logging.getLogger(__name__)

# One agent run at a time per contact: two messages sent in quick succession
# must not produce two overlapping replies.
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Media the agent cannot read, but that a human should see.
ESCALATING_MEDIA = {"image", "video", "document", "audio", "voice"}

UNREADABLE_MEDIA_REPLY = (
    "Thanks! I can't open attachments, so I've passed this to our team — "
    "someone will reply shortly."
)


async def process_inbound(message: InboundMessage, business_id: str | None = None) -> None:
    """Handle one inbound WhatsApp message. Never raises."""
    business_id = business_id or settings.business_id
    try:
        if await db.messages.exists(message.wa_message_id):
            log.info("duplicate webhook delivery ignored",
                     extra={"wa_message_id": message.wa_message_id})
            return

        async with _locks[message.wa_id]:
            await _process(message, business_id)
    except Exception:
        log.exception(
            "inbound processing failed",
            extra={"wa_id": message.wa_id, "wa_message_id": message.wa_message_id},
        )
    finally:
        lock = _locks.get(message.wa_id)
        if lock is not None and not lock.locked():
            _locks.pop(message.wa_id, None)


async def _process(message: InboundMessage, business_id: str) -> None:
    contact = await db.contacts.get_or_create(
        business_id, message.wa_id, name=message.profile_name
    )
    contact_id = str(contact["id"])

    saved = await db.messages.save(
        business_id=business_id,
        contact_id=contact_id,
        direction="in",
        sender="customer",
        body=message.text,
        message_type=message.type,
        wa_message_id=message.wa_message_id,
        status="delivered",
        created_at=message.timestamp,
    )
    if saved is None:
        # Another delivery of the same message won the race.
        log.info("duplicate message row, stopping",
                 extra={"wa_message_id": message.wa_message_id})
        return

    # Opens the 24-hour free-text window.
    contact = (
        await db.contacts.touch_inbound(
            business_id, contact_id, at=message.timestamp, name=message.profile_name
        )
        or contact
    )
    await db.contacts.bump_unread(business_id, contact_id)

    client = get_client()
    await client.mark_read(message.wa_message_id)

    if contact.get("human_takeover"):
        log.info("human is handling this chat, agent silent", extra={"contact_id": contact_id})
        return

    if not message.is_supported:
        await _handle_unreadable(message, contact, business_id)
        return

    reply = await run_agent(
        business_id=business_id,
        contact=contact,
        incoming_text=message.text or "",
    )

    if reply.escalated:
        # Re-read: escalate_to_human flipped the flag underneath us.
        contact = await db.contacts.get_by_id(business_id, contact_id) or contact

    result = await outbound.send_text(
        business_id=business_id, contact=contact, body=reply.text, sender="agent"
    )
    if not result.ok:
        log.error(
            "agent reply not delivered",
            extra={"contact_id": contact_id, "reason": result.reason},
        )


async def _handle_unreadable(
    message: InboundMessage, contact: dict[str, Any], business_id: str
) -> None:
    """Media without a caption: the agent cannot read it, so a human should."""
    if message.type not in ESCALATING_MEDIA:
        log.info("ignoring unsupported message type", extra={"type": message.type})
        return

    await db.contacts.set_takeover(business_id, str(contact["id"]), True, by="agent")
    await db.notes.add(
        business_id=business_id,
        contact_id=str(contact["id"]),
        note=f"Sent a {message.type} the agent cannot read.",
        created_by="agent",
    )
    await outbound.send_text(
        business_id=business_id,
        contact=contact,
        body=UNREADABLE_MEDIA_REPLY,
        sender="agent",
    )


async def process_status(update: StatusUpdate) -> None:
    """Apply a delivery receipt to the message we sent. Never raises."""
    try:
        await db.messages.update_status(update.wa_message_id, update.status, update.error)
        if update.status == "failed":
            log.error(
                "outbound message failed at Meta",
                extra={
                    "wa_message_id": update.wa_message_id,
                    "recipient": update.recipient_id,
                    "error": update.error,
                },
            )
    except Exception:
        log.exception("status update failed", extra={"wa_message_id": update.wa_message_id})
