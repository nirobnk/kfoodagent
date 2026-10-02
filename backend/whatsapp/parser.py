"""Turn Meta's nested webhook JSON into flat objects the rest of the app uses.

Meta sends three shapes to the same endpoint:
  1. inbound messages
  2. status updates for messages we sent (sent/delivered/read/failed)
  3. other change types we do not care about

This module never raises on a payload it does not understand: a webhook that
throws is a webhook Meta retries forever. Unknown shapes come back empty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

TEXT_TYPES = {"text"}
MEDIA_TYPES = {"image", "audio", "video", "document", "sticker", "voice"}


@dataclass(slots=True)
class InboundMessage:
    wa_id: str
    wa_message_id: str
    timestamp: datetime
    type: str
    phone_number_id: str
    text: str | None = None
    profile_name: str | None = None
    media_id: str | None = None
    media_mime: str | None = None
    caption: str | None = None
    # A document's own file name, as the customer's phone had it.
    media_filename: str | None = None
    # Set when the customer arrived by tapping a click-to-WhatsApp ad.
    referral: dict[str, Any] | None = None
    # The message this one replies to (swipe-to-reply), by Meta's id.
    reply_to: str | None = None
    forwarded: bool = False
    # A reaction: the emoji ("" when one is taken back) and what it is on.
    reaction_emoji: str | None = None
    reaction_to: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_supported(self) -> bool:
        """Can the agent act on this message as it stands?"""
        return bool(self.text) and self.type != "reaction"


@dataclass(slots=True)
class StatusUpdate:
    wa_message_id: str
    status: str
    recipient_id: str
    timestamp: datetime
    error: str | None = None


@dataclass(slots=True)
class ParsedWebhook:
    messages: list[InboundMessage] = field(default_factory=list)
    statuses: list[StatusUpdate] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.messages and not self.statuses


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _extract_text(message: dict[str, Any]) -> str | None:
    """Pull human-readable text out of whichever message shape arrived."""
    mtype = message.get("type")

    if mtype == "text":
        return (message.get("text") or {}).get("body")

    if mtype == "button":
        return (message.get("button") or {}).get("text")

    if mtype == "interactive":
        interactive = message.get("interactive") or {}
        for key in ("button_reply", "list_reply"):
            reply = interactive.get(key) or {}
            if reply.get("title"):
                return reply["title"]
        return None

    if mtype in MEDIA_TYPES:
        # A caption is usable text; a bare photo is not.
        return (message.get(mtype) or {}).get("caption")

    if mtype == "location":
        loc = message.get("location") or {}
        place = ", ".join(str(p) for p in (loc.get("name"), loc.get("address")) if p)
        lat, lng = loc.get("latitude"), loc.get("longitude")
        link = f"https://maps.google.com/?q={lat},{lng}" if lat is not None and lng is not None else ""
        text = " — ".join(p for p in (place, link) if p)
        return f"[location] {text}" if text else None

    if mtype == "contacts":
        return _contacts_text(message.get("contacts") or [])

    return None


def _referral(message: dict[str, Any]) -> dict[str, Any] | None:
    """The ad a customer tapped to start this chat, if they came from one.

    Meta sends it on the first message after the tap, under `referral`.
    """
    referral = message.get("referral")
    if not isinstance(referral, dict) or not referral:
        return None

    def text(key: str) -> str | None:
        value = referral.get(key)
        return str(value).strip() or None if value is not None else None

    return {
        "source_type": text("source_type"),
        "source_id": text("source_id"),
        "source_url": text("source_url"),
        "headline": text("headline"),
        "body": text("body"),
        "media_type": text("media_type"),
        "media_url": text("image_url") or text("video_url"),
        "ctwa_clid": text("ctwa_clid"),
        "raw": referral,
    }


def _contacts_text(cards: list[Any]) -> str | None:
    """A shared contact card, as one line per person: name and numbers."""
    people = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        name = ((card.get("name") or {}).get("formatted_name") or "").strip()
        phones = [
            str(p.get("phone") or p.get("wa_id") or "").strip()
            for p in card.get("phones") or [] if isinstance(p, dict)
        ]
        line = " ".join(p for p in [name or "Unnamed contact", *[x for x in phones if x]] if p)
        people.append(line)
    return f"[shared contact] {'; '.join(people)}" if people else None


def parse_webhook(payload: dict[str, Any]) -> ParsedWebhook:
    """Parse a full webhook body. Never raises."""
    result = ParsedWebhook()

    if not isinstance(payload, dict):
        return result

    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") not in (None, "messages"):
                continue

            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue

            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")

            profiles: dict[str, str] = {}
            for contact in value.get("contacts") or []:
                wa_id = str(contact.get("wa_id") or "")
                name = ((contact.get("profile") or {}).get("name") or "").strip()
                if wa_id and name:
                    profiles[wa_id] = name

            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                wa_id = str(message.get("from") or "")
                wa_message_id = str(message.get("id") or "")
                if not wa_id or not wa_message_id:
                    log.warning("skipping message with no from/id", extra={"payload": message})
                    continue

                mtype = str(message.get("type") or "unknown")
                media = message.get(mtype) if mtype in MEDIA_TYPES else None
                media = media if isinstance(media, dict) else {}

                context = message.get("context") or {}
                reaction = message.get("reaction") or {}
                result.messages.append(
                    InboundMessage(
                        wa_id=wa_id,
                        wa_message_id=wa_message_id,
                        timestamp=_ts(message.get("timestamp")),
                        type=mtype,
                        phone_number_id=phone_number_id,
                        text=_extract_text(message),
                        profile_name=profiles.get(wa_id),
                        media_id=media.get("id"),
                        media_mime=media.get("mime_type"),
                        caption=media.get("caption"),
                        media_filename=media.get("filename"),
                        referral=_referral(message),
                        # A forwarded message carries "forwarded" in its context
                        # and no id worth quoting.
                        reply_to=(
                            str(context["id"])
                            if context.get("id") and not context.get("forwarded")
                            and not context.get("frequently_forwarded")
                            else None
                        ),
                        forwarded=bool(
                            context.get("forwarded") or context.get("frequently_forwarded")
                        ),
                        reaction_emoji=(
                            str(reaction.get("emoji") or "") if mtype == "reaction" else None
                        ),
                        reaction_to=(
                            str(reaction["message_id"])
                            if mtype == "reaction" and reaction.get("message_id") else None
                        ),
                        raw=message,
                    )
                )

            for status in value.get("statuses") or []:
                if not isinstance(status, dict):
                    continue
                wa_message_id = str(status.get("id") or "")
                if not wa_message_id:
                    continue
                errors = status.get("errors") or []
                error = None
                if errors and isinstance(errors[0], dict):
                    error = errors[0].get("title") or errors[0].get("message")
                result.statuses.append(
                    StatusUpdate(
                        wa_message_id=wa_message_id,
                        status=str(status.get("status") or "unknown"),
                        recipient_id=str(status.get("recipient_id") or ""),
                        timestamp=_ts(status.get("timestamp")),
                        error=error,
                    )
                )

    return result
