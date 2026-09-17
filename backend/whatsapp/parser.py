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
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_supported(self) -> bool:
        """Can the agent act on this message as it stands?"""
        return bool(self.text)


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
        name = loc.get("name") or loc.get("address")
        if name:
            return f"[location] {name}"
        if loc.get("latitude") is not None:
            return f"[location] {loc.get('latitude')},{loc.get('longitude')}"

    return None


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
