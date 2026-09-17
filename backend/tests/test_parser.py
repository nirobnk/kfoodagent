"""Parser tests. Meta's payloads are nested and inconsistent; these pin the shapes."""

from __future__ import annotations

from datetime import timezone

from whatsapp.parser import parse_webhook


def envelope(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}],
    }


def test_text_message():
    payload = envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "9477", "phone_number_id": "PNID"},
            "contacts": [{"profile": {"name": "Nimal"}, "wa_id": "94771234567"}],
            "messages": [
                {
                    "from": "94771234567",
                    "id": "wamid.ABC",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": "Mokakda thiyenne?"},
                }
            ],
        }
    )

    parsed = parse_webhook(payload)

    assert len(parsed.messages) == 1
    message = parsed.messages[0]
    assert message.wa_id == "94771234567"
    assert message.text == "Mokakda thiyenne?"
    assert message.wa_message_id == "wamid.ABC"
    assert message.profile_name == "Nimal"
    assert message.phone_number_id == "PNID"
    assert message.timestamp.tzinfo == timezone.utc
    assert message.is_supported


def test_status_payload_has_no_messages():
    payload = envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": "PNID"},
            "statuses": [
                {
                    "id": "wamid.OUT",
                    "status": "delivered",
                    "timestamp": "1700000100",
                    "recipient_id": "94771234567",
                }
            ],
        }
    )

    parsed = parse_webhook(payload)

    assert parsed.messages == []
    assert len(parsed.statuses) == 1
    assert parsed.statuses[0].status == "delivered"
    assert parsed.statuses[0].wa_message_id == "wamid.OUT"


def test_failed_status_carries_the_error():
    payload = envelope(
        {
            "statuses": [
                {
                    "id": "wamid.OUT",
                    "status": "failed",
                    "timestamp": "1700000100",
                    "recipient_id": "94771234567",
                    "errors": [{"code": 131047, "title": "Re-engagement message"}],
                }
            ]
        }
    )

    status = parse_webhook(payload).statuses[0]

    assert status.status == "failed"
    assert status.error == "Re-engagement message"


def test_image_without_caption_is_not_supported():
    payload = envelope(
        {
            "messages": [
                {
                    "from": "94771234567",
                    "id": "wamid.IMG",
                    "timestamp": "1700000000",
                    "type": "image",
                    "image": {"id": "MEDIA1", "mime_type": "image/jpeg"},
                }
            ]
        }
    )

    message = parse_webhook(payload).messages[0]

    assert message.type == "image"
    assert message.media_id == "MEDIA1"
    assert message.text is None
    assert not message.is_supported


def test_image_caption_is_used_as_text():
    payload = envelope(
        {
            "messages": [
                {
                    "from": "94771234567",
                    "id": "wamid.IMG2",
                    "timestamp": "1700000000",
                    "type": "image",
                    "image": {"id": "M", "mime_type": "image/jpeg", "caption": "Is this ramen?"},
                }
            ]
        }
    )

    message = parse_webhook(payload).messages[0]

    assert message.text == "Is this ramen?"
    assert message.is_supported


def test_interactive_button_reply():
    payload = envelope(
        {
            "messages": [
                {
                    "from": "94771234567",
                    "id": "wamid.BTN",
                    "timestamp": "1700000000",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "confirm", "title": "Yes, order it"},
                    },
                }
            ]
        }
    )

    assert parse_webhook(payload).messages[0].text == "Yes, order it"


def test_garbage_payloads_do_not_raise():
    for payload in ({}, {"entry": None}, {"entry": [{"changes": [{}]}]}, {"entry": ["x"]}):
        assert parse_webhook(payload).is_empty

    # A message with no id is skipped rather than crashing the webhook.
    payload = envelope({"messages": [{"from": "9477", "type": "text", "text": {"body": "hi"}}]})
    assert parse_webhook(payload).is_empty


def test_multiple_messages_in_one_delivery():
    payload = envelope(
        {
            "messages": [
                {"from": "9477", "id": "a", "timestamp": "1700000000", "type": "text",
                 "text": {"body": "one"}},
                {"from": "9477", "id": "b", "timestamp": "1700000001", "type": "text",
                 "text": {"body": "two"}},
            ]
        }
    )

    parsed = parse_webhook(payload)

    assert [m.text for m in parsed.messages] == ["one", "two"]
