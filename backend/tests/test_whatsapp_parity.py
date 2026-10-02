# ruff: noqa: F811 — pytest fixtures are imported, then named as arguments.
"""Everything a WhatsApp chat carries: files, stickers, voice notes, replies, reactions."""

from __future__ import annotations

from dataclasses import replace

import handlers
from agent.graph import _to_lc_message
from tests.conftest import BUSINESS_ID
from tests.test_api import client, seeded_contact  # noqa: F401 — fixtures
from tests.test_api import wired as api_env  # noqa: F401 — a fixture
from tests.test_handlers import inbound, wired  # noqa: F401 — a fixture
from vision import ImageAnalysis
from whatsapp import DownloadedMedia
from whatsapp.parser import parse_webhook

PDF = DownloadedMedia(b"%PDF-1.4 receipt", "application/pdf", "receipt.pdf")


def envelope(message: dict) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "PNID"}, "messages": [message],
    }}]}]}


def base(**extra) -> dict:
    return {"from": "94771234567", "id": "wamid.X", "timestamp": "1700000000", **extra}


# --- the webhook --------------------------------------------------------------

def test_a_document_keeps_its_file_name():
    [m] = parse_webhook(envelope(base(type="document", document={
        "id": "media-1", "mime_type": "application/pdf", "filename": "HNB receipt.pdf",
    }))).messages
    assert m.media_filename == "HNB receipt.pdf"
    assert m.media_mime == "application/pdf"


def test_a_swipe_reply_carries_the_quoted_message():
    [m] = parse_webhook(envelope(base(type="text", text={"body": "this one"},
                                      context={"from": "9477", "id": "wamid.ORIGINAL"}))).messages
    assert m.reply_to == "wamid.ORIGINAL" and not m.forwarded


def test_a_forwarded_message_is_marked_and_quotes_nothing():
    [m] = parse_webhook(envelope(base(type="text", text={"body": "Shin Rs 600?"},
                                      context={"forwarded": True}))).messages
    assert m.forwarded and m.reply_to is None


def test_a_reaction_is_an_emoji_on_a_message_and_never_answered():
    [m] = parse_webhook(envelope(base(type="reaction", reaction={
        "message_id": "wamid.OURS", "emoji": "❤️",
    }))).messages
    assert (m.reaction_emoji, m.reaction_to) == ("❤️", "wamid.OURS")
    assert not m.is_supported


def test_a_shared_contact_reads_as_a_name_and_number():
    [m] = parse_webhook(envelope(base(type="contacts", contacts=[{
        "name": {"formatted_name": "Levi Perera"},
        "phones": [{"phone": "+94 77 123 4567", "wa_id": "94771234567"}],
    }]))).messages
    assert m.text == "[shared contact] Levi Perera +94 77 123 4567"


def test_a_location_pin_carries_a_map_link():
    [m] = parse_webhook(envelope(base(type="location", location={
        "latitude": 6.9271, "longitude": 79.8612, "name": "Home",
    }))).messages
    assert m.text == "[location] Home — https://maps.google.com/?q=6.9271,79.8612"


# --- what happens to it -------------------------------------------------------

def doc(mime: str, name: str, wa_id: str = "wamid.DOC", caption: str | None = None):
    return replace(inbound(caption, wa_id, mtype="document", media_id="m-doc", media_mime=mime),
                   media_filename=name)


async def test_a_pdf_receipt_is_kept_and_read(wired, monkeypatch):
    """Rangi's PDF receipt on Oct 2 was neither read nor shown."""
    fake, wa, calls = wired
    wa.media_downloads["m-doc"] = PDF

    async def describe(media, *, catalogue):
        assert media.mime_type == "application/pdf"
        return ImageAnalysis(kind="payment_slip", description="A transfer of LKR 4,150.00.")

    monkeypatch.setattr(handlers, "describe_image", describe)

    await handlers.process_inbound(doc("application/pdf", "receipt.pdf"), BUSINESS_ID)

    [row] = fake.rows("messages")[:1]
    assert row["media_path"].endswith(".pdf")
    assert row["media_mime"] == "application/pdf"
    assert row["media_filename"] == "receipt.pdf"
    assert row["image_description"] == "Payment slip. A transfer of LKR 4,150.00."
    assert calls == [""], "the agent answers it"
    assert "what it shows: Payment slip" in _to_lc_message(row).content


async def test_a_file_nobody_can_read_is_still_kept_and_named(wired, monkeypatch):
    fake, wa, calls = wired
    wa.media_downloads["m-doc"] = DownloadedMedia(b"PK..", "application/vnd.ms-excel", "list.xls")

    async def never(*_, **__):
        raise AssertionError("an Excel file is not sent to the vision model")

    monkeypatch.setattr(handlers, "describe_image", never)

    await handlers.process_inbound(doc("application/vnd.ms-excel", "order list.xls"), BUSINESS_ID)

    row = fake.rows("messages")[0]
    assert row["media_path"].endswith(".xls")
    assert row["image_analysis_status"] is None
    assert _to_lc_message(row).content.startswith('[document "order list.xls"]')


async def test_a_voice_note_is_kept_as_well_as_transcribed(wired, monkeypatch):
    fake, wa, calls = wired
    wa.media_downloads["m-voice"] = DownloadedMedia(b"OggS..", "audio/ogg; codecs=opus", "v.ogg")

    async def transcribe(media):
        return "Shin black eka kiyada"

    monkeypatch.setattr(handlers, "transcribe_audio", transcribe)

    await handlers.process_inbound(
        inbound(None, "wamid.V", mtype="audio", media_id="m-voice", media_mime="audio/ogg"),
        BUSINESS_ID,
    )

    row = fake.rows("messages")[0]
    assert row["media_path"].endswith(".ogg"), "staff can play it"
    assert row["transcript"] == "Shin black eka kiyada"
    assert wa.downloaded_media_ids == ["m-voice"], "downloaded once, used twice"


async def test_a_sticker_is_kept_and_not_answered(wired):
    fake, wa, calls = wired
    wa.media_downloads["m-st"] = DownloadedMedia(b"RIFF....WEBP", "image/webp", "s.webp")

    await handlers.process_inbound(
        inbound(None, "wamid.ST", mtype="sticker", media_id="m-st", media_mime="image/webp"),
        BUSINESS_ID,
    )

    assert fake.rows("messages")[0]["media_path"].endswith(".webp")
    assert calls == []


async def test_a_reaction_is_kept_quietly(wired):
    fake, wa, calls = wired
    contact_before = None
    await handlers.process_inbound(inbound("hi", "wamid.1"), BUSINESS_ID)
    contact_before = dict(fake.rows("contacts")[0])
    reaction = replace(inbound(None, "wamid.R", mtype="reaction"),
                       reaction_emoji="👍", reaction_to="wamid.OUT1")

    await handlers.process_inbound(reaction, BUSINESS_ID)

    row = next(m for m in fake.rows("messages") if m["message_type"] == "reaction")
    assert row["body"] == "👍" and row["reacted_to_wa_message_id"] == "wamid.OUT1"
    assert calls == ["hi"], "no answer to a thumbs up"
    assert len(wa.texts) == 1, "not even the takeover acknowledgement"
    contact = fake.rows("contacts")[0]
    assert contact["unread_count"] == contact_before["unread_count"]
    assert contact["last_customer_message_at"] == contact_before["last_customer_message_at"]


async def test_a_reply_keeps_what_it_quotes(wired):
    fake, wa, calls = wired
    await handlers.process_inbound(inbound("hi", "wamid.1"), BUSINESS_ID)
    agent_reply = next(m for m in fake.rows("messages") if m["direction"] == "out")

    reply = replace(inbound("ow meka", "wamid.2"), reply_to=agent_reply["wa_message_id"])
    await handlers.process_inbound(reply, BUSINESS_ID)

    row = next(m for m in fake.rows("messages") if m.get("wa_message_id") == "wamid.2")
    assert row["reply_to_text"] == "reply to hi"
    assert _to_lc_message(row).content == '[replying to: "reply to hi"] ow meka'


async def test_the_customer_sees_typing_while_the_agent_works(wired):
    fake, wa, calls = wired

    await handlers.process_inbound(inbound("price?", "wamid.T"), BUSINESS_ID)

    assert wa.typing == ["wamid.T"]


def test_reactions_are_not_turns_for_the_agent():
    from agent import graph

    rows = [{"direction": "in", "body": "hi", "message_type": "text"},
            {"direction": "in", "body": "👍", "message_type": "reaction"}]
    kept = [r for r in rows if r.get("message_type") != "reaction"]
    assert [graph._to_lc_message(r).content for r in kept] == ["hi"]


# --- staff reply and react ----------------------------------------------------

def customer_message(fake, contact, body="Shin black eka kiyada", wa_id="wamid.IN1"):
    return fake.new_row("messages", {
        "business_id": BUSINESS_ID, "contact_id": contact["id"], "direction": "in",
        "sender": "customer", "body": body, "message_type": "text", "wa_message_id": wa_id,
        "status": "delivered",
    })


def test_staff_can_reply_to_a_specific_message(client, api_env):  # noqa: F811
    fake, wa = api_env
    contact = seeded_contact(fake)
    quoted = customer_message(fake, contact)
    fake.seed("messages", [quoted])

    response = client.post("/messages/send", json={
        "contact_id": contact["id"], "body": "Rs. 895 😊", "reply_to_message_id": quoted["id"],
    })

    assert response.json()["ok"] is True
    assert wa.replies_to == ["wamid.IN1"]
    sent = next(m for m in fake.rows("messages") if m["direction"] == "out")
    assert sent["reply_to_text"] == "Shin black eka kiyada"


def test_staff_can_react_without_taking_the_chat_over(client, api_env):  # noqa: F811
    fake, wa = api_env
    contact = seeded_contact(fake)
    target = customer_message(fake, contact)
    fake.seed("messages", [target])

    response = client.post(f"/messages/{target['id']}/react", json={"emoji": "❤️"})

    assert response.json()["ok"] is True
    assert wa.reactions == [("94771234567", "wamid.IN1", "❤️")]
    row = next(m for m in fake.rows("messages") if m["message_type"] == "reaction")
    assert row["direction"] == "out" and row["reacted_to_wa_message_id"] == "wamid.IN1"
    assert fake.rows("contacts")[0]["human_takeover"] is False


def test_a_reaction_needs_the_window_open(client, api_env):  # noqa: F811
    fake, wa = api_env
    contact = seeded_contact(fake, hours_ago=30)
    target = customer_message(fake, contact)
    fake.seed("messages", [target])

    response = client.post(f"/messages/{target['id']}/react", json={"emoji": "👍"})

    assert response.json()["reason"] == "window_closed"
    assert wa.reactions == []


def test_a_reply_to_another_chat_s_message_is_refused(client, api_env):  # noqa: F811
    fake, wa = api_env
    contact = seeded_contact(fake)
    elsewhere = customer_message(fake, {"id": "44444444-4444-4444-4444-444444444444"})
    fake.seed("messages", [elsewhere])

    response = client.post("/messages/send", json={
        "contact_id": contact["id"], "body": "x", "reply_to_message_id": elsewhere["id"],
    })

    assert response.status_code == 404
