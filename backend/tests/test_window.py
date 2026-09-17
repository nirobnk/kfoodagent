"""24-hour window. Getting this wrong means silent send failures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from whatsapp.window import (
    can_send_free_text,
    format_remaining,
    window_expires_at,
    window_remaining,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def contact_at(delta: timedelta | None) -> dict:
    if delta is None:
        return {"last_customer_message_at": None}
    return {"last_customer_message_at": (NOW - delta).isoformat()}


def test_never_messaged_cannot_get_free_text():
    assert can_send_free_text(contact_at(None), at=NOW) is False
    assert can_send_free_text({}, at=NOW) is False


def test_inside_the_window():
    assert can_send_free_text(contact_at(timedelta(hours=1)), at=NOW) is True
    assert can_send_free_text(contact_at(timedelta(hours=23, minutes=59)), at=NOW) is True


def test_outside_the_window():
    assert can_send_free_text(contact_at(timedelta(hours=24)), at=NOW) is False
    assert can_send_free_text(contact_at(timedelta(days=3)), at=NOW) is False


def test_naive_timestamps_are_treated_as_utc():
    contact = {"last_customer_message_at": (NOW - timedelta(hours=2)).replace(tzinfo=None)}
    assert can_send_free_text(contact, at=NOW) is True


def test_postgres_style_timestamps_parse():
    for value in (
        "2026-09-17T10:00:00Z",
        "2026-09-17T10:00:00+00:00",
        "2026-09-17T10:00:00.123456+00:00",
        "2026-09-17T10:00:00.123456789+00:00",  # nanosecond precision
    ):
        assert can_send_free_text({"last_customer_message_at": value}, at=NOW) is True


def test_unparseable_timestamp_fails_closed():
    assert can_send_free_text({"last_customer_message_at": "not a date"}, at=NOW) is False


def test_remaining_time():
    contact = contact_at(timedelta(hours=20))
    assert window_expires_at(contact) == NOW + timedelta(hours=4)
    assert window_remaining(contact, at=NOW) == timedelta(hours=4)
    assert window_remaining(contact_at(timedelta(days=5)), at=NOW) == timedelta(0)
    assert window_remaining({}, at=NOW) == timedelta(0)


def test_format_remaining():
    assert format_remaining(timedelta(hours=4, minutes=12)) == "4h 12m"
    assert format_remaining(timedelta(minutes=45)) == "45m"
    assert format_remaining(timedelta(0)) == "expired"
