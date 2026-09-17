"""The 24-hour customer service window.

Inside the window we may send free-form text. Outside it, Meta only accepts an
approved template. Every outbound send checks this first.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

WINDOW = timedelta(hours=24)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # Postgres returns microseconds at arbitrary precision; fromisoformat
        # in older runtimes wants exactly 0 or 6 digits.
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            if "." in text:
                head, _, tail = text.partition(".")
                digits = "".join(c for c in tail if c.isdigit())[:6]
                offset = tail[len(digits) :].lstrip("0123456789")
                try:
                    parsed = datetime.fromisoformat(f"{head}.{digits.ljust(6, '0')}{offset}")
                except ValueError:
                    return None
            else:
                return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def last_customer_message_at(contact: Mapping[str, Any]) -> datetime | None:
    return _parse(contact.get("last_customer_message_at"))


def can_send_free_text(contact: Mapping[str, Any], *, at: datetime | None = None) -> bool:
    last = last_customer_message_at(contact)
    if last is None:
        return False
    return ((at or now_utc()) - last) < WINDOW


def window_expires_at(contact: Mapping[str, Any]) -> datetime | None:
    last = last_customer_message_at(contact)
    return None if last is None else last + WINDOW


def window_remaining(contact: Mapping[str, Any], *, at: datetime | None = None) -> timedelta:
    expires = window_expires_at(contact)
    if expires is None:
        return timedelta(0)
    remaining = expires - (at or now_utc())
    return remaining if remaining > timedelta(0) else timedelta(0)


def format_remaining(remaining: timedelta) -> str:
    total = int(remaining.total_seconds())
    if total <= 0:
        return "expired"
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"
