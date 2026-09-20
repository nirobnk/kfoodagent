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

# Media the agent cannot open. It still answers these: the commonest
# attachment this shop receives is a bank slip sent with no caption at all,
# and the old behaviour — silent takeover plus a canned "I can't open
# attachments" — dropped every one of those customers mid-sale. The agent sees
# the attachment marked as unreadable in its history and handles it the way a
# person would: recognise what it almost certainly is, take it, say thank you.
# A sticker stays out: it is the WhatsApp equivalent of a thumbs up, and
# paying for a reply to one is money spent on nothing.
AGENT_HANDLED_MEDIA = {"image", "video", "document", "audio", "voice"}

# Said once, by the shop, while a person is picking the chat up. Not an
# apology and not a promise of a time — just an answer, so that writing into
# this chat does not feel like writing into a dead number.
TAKEOVER_ACK = "Got your message 🙏 I'm looking into this now and will come back to you shortly."


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
        # The agent stays out of it — but silence is not a neutral act. A
        # customer who wrote "I need shin red one noodles packet" and then
        # "Please reply" into a chat nobody had picked up got nothing at all,
        # because takeover was treated as "send nothing, ever". Answer once,
        # then leave it to the person who now owns it.
        await _acknowledge_takeover(contact, business_id)
        log.info("human is handling this chat, agent silent", extra={"contact_id": contact_id})
        return

    if not message.is_supported and message.type not in AGENT_HANDLED_MEDIA:
        log.info("ignoring unsupported message type", extra={"type": message.type})
        return

    reply = await run_agent(
        business_id=business_id,
        contact=contact,
        incoming_text=message.text or "",
    )

    if reply.escalated:
        # Re-read: escalate_to_human flipped the flag underneath us.
        contact = await db.contacts.get_by_id(business_id, contact_id) or contact

    if reply.flagged:
        # Staff have a task waiting, but this chat is still the agent's. Worth
        # a line in the log precisely because nothing else changes.
        log.info(
            "flagged for staff, agent still serving",
            extra={"contact_id": contact_id, "reason": reply.flag_reason},
        )

    if reply.payment_reported:
        # A slip nobody has checked yet. The order carries the flag and a task
        # is already on the list, so the chat stays with the agent — but the
        # unread badge makes sure the dashboard shows it needs an eye.
        log.info(
            "payment reported by customer",
            extra={
                "contact_id": contact_id,
                "order_number": (reply.payment_order or {}).get("order_number"),
            },
        )

    result = await outbound.send_text(
        business_id=business_id, contact=contact, body=reply.text, sender="agent"
    )
    if not result.ok:
        log.error(
            "agent reply not delivered",
            extra={"contact_id": contact_id, "reason": result.reason},
        )


async def _acknowledge_takeover(contact: dict[str, Any], business_id: str) -> None:
    """Reply once, and only once, while a chat sits in human takeover.

    "Once" is judged by whether anything at all has gone out since the
    takeover began: a staff reply counts, so a customer never gets this on top
    of a real answer, and a second or third message from them does not
    produce a second or third apology.
    """
    started_at = contact.get("takeover_started_at")
    if not started_at:
        return

    try:
        if await db.messages.any_outbound_since(str(contact["id"]), str(started_at)):
            return
        await outbound.send_text(
            business_id=business_id, contact=contact, body=TAKEOVER_ACK, sender="agent"
        )
        log.info("acknowledged a message during takeover", extra={"contact_id": contact["id"]})
    except Exception:
        log.exception(
            "could not acknowledge during takeover", extra={"contact_id": contact.get("id")}
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
