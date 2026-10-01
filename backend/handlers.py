"""What happens to a message after the webhook has answered 200.

Order of operations for an inbound message — this order matters:
  1. idempotency check   (Meta retries; we must not answer twice)
  2. contact upsert
  3. persist the message
  4. touch the 24-hour window
  5. wait briefly for the customer's next message, and let the last one of a
     burst answer for all of them
  6. human_takeover check (the agent stays silent while staff are handling it)
  7. run the agent
  8. send exactly one reply
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import db
import outbound
from agent import run_agent
from config import settings
from transcription import transcribe_audio
from vision import describe_image
from whatsapp import InboundMessage, StatusUpdate, get_client

log = logging.getLogger(__name__)

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


@dataclass(slots=True)
class Prepared:
    """One inbound message, saved and ready for the agent to read."""

    message: InboundMessage
    contact: dict[str, Any]
    saved: dict[str, Any]
    incoming_text: str
    client: Any


@dataclass
class _Chat:
    """One customer's messages while they are being handled.

    Saving is serialised by `prepare`, replying by `reply`, so a message can be
    saved while the reply to the one before it is still being written.
    `latest` is the newest message that wants an answer: a message that is no
    longer the latest once its wait is over leaves the answer to the newer
    one, which reads both. `batch` holds the saved messages that reply will
    cover.

    Before this, "Epa epa" and "Mn kiynnm" sent a second apart were each
    answered on their own, and the customer got the same reply twice.
    """

    prepare: asyncio.Lock = field(default_factory=asyncio.Lock)
    reply: asyncio.Lock = field(default_factory=asyncio.Lock)
    latest: str | None = None
    batch: list[Prepared] = field(default_factory=list)
    users: int = 0


_chats: dict[str, _Chat] = {}


def _expects_reply(message: InboundMessage) -> bool:
    return message.is_supported or message.type in AGENT_HANDLED_MEDIA


async def process_inbound(message: InboundMessage, business_id: str | None = None) -> None:
    """Handle one inbound WhatsApp message. Never raises."""
    business_id = business_id or settings.business_id
    chat = _chats.setdefault(message.wa_id, _Chat())
    chat.users += 1
    try:
        if await db.messages.exists(message.wa_message_id):
            log.info("duplicate webhook delivery ignored",
                     extra={"wa_message_id": message.wa_message_id})
            return

        expects_reply = _expects_reply(message)
        if expects_reply:
            chat.latest = message.wa_message_id

        try:
            async with chat.prepare:
                prepared = await _prepare(message, business_id)
        except Exception:
            log.exception(
                "inbound processing failed",
                extra={"wa_id": message.wa_id, "wa_message_id": message.wa_message_id},
            )
            # Earlier messages were left for this one to answer. Answer them.
            if chat.latest == message.wa_message_id and chat.batch:
                await _answer_batch(chat, message.wa_message_id, business_id)
            return
        if prepared is None:
            return

        if not expects_reply:
            # Nothing to say to a sticker, but a chat in takeover still gets
            # its one acknowledgement.
            async with chat.reply:
                await _respond([prepared], business_id)
            return

        chat.batch.append(prepared)
        if settings.reply_batch_seconds:
            await asyncio.sleep(settings.reply_batch_seconds)
        if chat.latest != message.wa_message_id:
            log.info("answered together with a later message",
                     extra={"wa_message_id": message.wa_message_id})
            return
        await _answer_batch(chat, message.wa_message_id, business_id)
    except Exception:
        log.exception(
            "inbound processing failed",
            extra={"wa_id": message.wa_id, "wa_message_id": message.wa_message_id},
        )
    finally:
        chat.users -= 1
        if chat.users == 0:
            _chats.pop(message.wa_id, None)


async def _answer_batch(chat: _Chat, wa_message_id: str, business_id: str) -> None:
    async with chat.reply:
        # A newer message may have arrived while the last reply was going out;
        # it answers for this batch, so do not answer twice.
        if chat.latest != wa_message_id or not chat.batch:
            return
        batch, chat.batch = chat.batch, []
        await _respond(batch, business_id)


async def _prepare(message: InboundMessage, business_id: str) -> Prepared | None:
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
        transcription_status=(
            "pending" if message.type in {"audio", "voice"} and message.media_id else None
        ),
        image_analysis_status=(
            "pending" if message.type == "image" and message.media_id else None
        ),
        created_at=message.timestamp,
    )
    if saved is None:
        # Another delivery of the same message won the race.
        log.info("duplicate message row, stopping",
                 extra={"wa_message_id": message.wa_message_id})
        return None

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

    incoming_text = message.text or ""
    if message.type in {"audio", "voice"} and message.media_id:
        incoming_text = await _transcribe_voice(message, str(saved["id"]), client)
    elif message.type == "image" and message.media_id:
        # The description lands on the message row, and the agent reads it
        # from history next to the caption. incoming_text stays the caption:
        # it is what the customer wrote, and the model's view of the photo
        # must not be passed off as their words.
        await _process_image(message, str(saved["id"]), business_id, contact_id, client)

    return Prepared(
        message=message,
        contact=contact,
        saved=saved,
        incoming_text=incoming_text,
        client=client,
    )


async def _respond(batch: list[Prepared], business_id: str) -> None:
    """Answer a burst of messages once, as a reply to the last of them.

    Every message in the burst is already saved, so the agent reads them all
    in its history.
    """
    last = batch[-1]
    message = last.message
    contact = last.contact
    contact_id = str(contact["id"])

    if contact.get("human_takeover"):
        # The agent stays out of it — but silence is not a neutral act. A
        # customer who wrote "I need shin red one noodles packet" and then
        # "Please reply" into a chat nobody had picked up got nothing at all,
        # because takeover was treated as "send nothing, ever". Answer once,
        # then leave it to the person who now owns it.
        await _acknowledge_takeover(contact, business_id)
        log.info("human is handling this chat, agent silent", extra={"contact_id": contact_id})
        return

    if not _expects_reply(message):
        log.info("ignoring unsupported message type", extra={"type": message.type})
        return

    reply = await run_agent(
        business_id=business_id,
        contact=contact,
        incoming_text=last.incoming_text,
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
        # The slip is the newest photo or file in the burst: "paid" typed a
        # second after the screenshot is about the screenshot.
        slip = next(
            (p for p in reversed(batch)
             if p.message.media_id and p.message.type in {"image", "document"}),
            last,
        )
        try:
            has_receipt_media = bool(
                slip.message.media_id and slip.message.type in {"image", "document"}
            )
            receipt = await db.payment_receipts.create(
                business_id=business_id,
                contact_id=contact_id,
                order_id=(reply.payment_order or {}).get("id"),
                message_id=str(slip.saved["id"]),
                whatsapp_media_id=slip.message.media_id,
                media_mime_type=slip.message.media_mime,
                reported_detail=(
                    (slip.message.text or "").strip()
                    or (message.text or "").strip()
                    or (
                        "Receipt submitted through WhatsApp"
                        if slip.message.media_id
                        else "Payment reported in chat"
                    )
                ),
                storage_status="pending" if has_receipt_media else "not_applicable",
            )
            if has_receipt_media:
                await _store_receipt_media(
                    message=slip.message,
                    receipt=receipt,
                    business_id=business_id,
                    contact_id=contact_id,
                    client=slip.client,
                )
        except Exception:
            # Do not strand a paying customer because the audit write failed.
            # The order/task created by record_payment_receipt still remains.
            log.exception(
                "could not store payment receipt record",
                extra={"contact_id": contact_id, "message_id": slip.saved.get("id")},
            )

    result = await outbound.send_text(
        business_id=business_id, contact=contact, body=reply.text, sender="agent"
    )
    if not result.ok:
        log.error(
            "agent reply not delivered",
            extra={"contact_id": contact_id, "reason": result.reason},
        )


async def _store_receipt_media(
    *,
    message: InboundMessage,
    receipt: dict[str, Any],
    business_id: str,
    contact_id: str,
    client: Any,
) -> None:
    """Copy expiring Meta media into private, durable Supabase Storage."""
    receipt_id = str(receipt["id"])
    try:
        media = await client.download_media(
            str(message.media_id), max_bytes=settings.receipt_max_bytes
        )
        await db.payment_receipts.store_media(
            receipt_id=receipt_id,
            business_id=business_id,
            contact_id=contact_id,
            content=media.content,
            mime_type=media.mime_type,
        )
    except Exception as exc:
        await db.payment_receipts.mark_storage_failed(
            business_id,
            receipt_id,
            f"{type(exc).__name__}: {exc}",
        )
        log.warning(
            "receipt media could not be stored",
            extra={"receipt_id": receipt_id, "error_type": type(exc).__name__},
        )


async def _transcribe_voice(
    message: InboundMessage, message_id: str, client: Any
) -> str:
    """Return usable text while making transcription failure non-fatal."""
    if not settings.voice_transcription_configured:
        error = "voice transcription is not configured"
        await db.messages.fail_transcription(message_id, error)
        log.warning(error, extra={"message_id": message_id})
        return message.text or ""

    try:
        media = await client.download_media(
            str(message.media_id), max_bytes=settings.voice_max_bytes
        )
        transcript = await transcribe_audio(media)
        await db.messages.complete_transcription(message_id, transcript)
        return transcript
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        await db.messages.fail_transcription(message_id, error)
        log.warning(
            "voice transcription failed",
            extra={"message_id": message_id, "error_type": type(exc).__name__},
        )
        return message.text or ""


async def _process_image(
    message: InboundMessage,
    message_id: str,
    business_id: str,
    contact_id: str,
    client: Any,
) -> None:
    """Keep the photo for staff and record what it shows. Never fatal.

    Downloaded once and used twice. If analysis fails the agent sees the photo
    as it did before analysis existed — an attachment it cannot open — and
    asks which product it is.
    """
    try:
        media = await client.download_media(
            str(message.media_id), max_bytes=settings.image_max_bytes
        )
    except Exception as exc:
        await db.messages.fail_image_analysis(
            message_id, f"download failed: {type(exc).__name__}: {exc}"
        )
        log.warning(
            "inbound photo could not be downloaded",
            extra={"message_id": message_id, "error_type": type(exc).__name__},
        )
        return

    try:
        # Meta's copy expires; without this the dashboard can never show it.
        await db.messages.store_media(
            message_id=message_id,
            business_id=business_id,
            contact_id=contact_id,
            content=media.content,
            mime_type=media.mime_type,
        )
    except Exception as exc:
        log.warning(
            "inbound photo could not be stored",
            extra={"message_id": message_id, "error_type": type(exc).__name__},
        )

    if not settings.image_analysis_configured:
        error = "image analysis is not configured"
        await db.messages.fail_image_analysis(message_id, error)
        log.warning(error, extra={"message_id": message_id})
        return

    try:
        catalogue = await _catalogue_names(business_id)
        analysis = await describe_image(media, catalogue=catalogue)
        await db.messages.complete_image_analysis(message_id, analysis.as_text())
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        await db.messages.fail_image_analysis(message_id, error)
        log.warning(
            "image analysis failed",
            extra={"message_id": message_id, "error_type": type(exc).__name__},
        )


async def _catalogue_names(business_id: str) -> list[str]:
    """Product names the vision model should match a photo against.

    A missing list only makes the match less exact, so a catalogue read that
    fails does not stop the photo being described.
    """
    try:
        variants = await db.menu.list_available(business_id)
    except Exception:
        log.warning("could not read catalogue for image analysis", exc_info=True)
        return []
    names: dict[str, None] = {}
    for row in variants:
        name = (row.get("product_name") or row.get("name") or "").strip()
        if name:
            names.setdefault(name, None)
    return list(names)


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
