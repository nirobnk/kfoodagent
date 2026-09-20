"""The inbound pipeline: dedupe, persist, window, takeover, one reply."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import db
import handlers
import outbound
from agent.graph import AgentReply
from tests.conftest import BUSINESS_ID, db_modules
from tests.fakes import FakeSupabase, FakeWhatsApp
from whatsapp import DownloadedMedia
from whatsapp.parser import InboundMessage


@pytest.fixture
def wired(monkeypatch):
    fake = FakeSupabase()
    wa = FakeWhatsApp()

    async def get_db():
        return fake

    for module in db_modules():
        monkeypatch.setattr(module, "get_db", get_db, raising=False)
    monkeypatch.setattr(handlers, "get_client", lambda: wa)
    monkeypatch.setattr(outbound, "get_client", lambda: wa)

    calls: list[str] = []

    async def fake_agent(*, business_id, contact, incoming_text, business_name="K-Food"):
        calls.append(incoming_text)
        return AgentReply(text=f"reply to {incoming_text}")

    monkeypatch.setattr(handlers, "run_agent", fake_agent)
    return fake, wa, calls


def inbound(
    text: str | None = "hello",
    wa_message_id: str = "wamid.1",
    mtype: str = "text",
    media_id: str | None = None,
    media_mime: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        wa_id="94771234567",
        wa_message_id=wa_message_id,
        timestamp=datetime.now(timezone.utc),
        type=mtype,
        phone_number_id="PNID",
        text=text,
        profile_name="Nimal",
        media_id=media_id,
        media_mime=media_mime,
    )


async def test_first_message_creates_contact_stores_and_replies(wired):
    fake, wa, calls = wired

    await handlers.process_inbound(inbound("what ramen do you have?"), BUSINESS_ID)

    contacts = fake.rows("contacts")
    assert len(contacts) == 1
    assert contacts[0]["wa_id"] == "94771234567"
    assert contacts[0]["name"] == "Nimal"
    assert contacts[0]["last_customer_message_at"] is not None, "the 24h window must be opened"
    assert contacts[0]["unread_count"] == 1

    stored = fake.rows("messages")
    assert [m["direction"] for m in stored] == ["in", "out"]
    assert calls == ["what ramen do you have?"]
    assert wa.texts == [("94771234567", "reply to what ramen do you have?")]
    assert wa.read_receipts == ["wamid.1"]


async def test_retried_delivery_does_not_reply_twice(wired):
    fake, wa, calls = wired

    await handlers.process_inbound(inbound("hi", "wamid.SAME"), BUSINESS_ID)
    await handlers.process_inbound(inbound("hi", "wamid.SAME"), BUSINESS_ID)

    assert len(calls) == 1, "the agent must run once per real message"
    assert len(wa.texts) == 1
    assert len([m for m in fake.rows("messages") if m["direction"] == "in"]) == 1


async def test_takeover_stops_the_agent_but_answers_once(wired):
    """Takeover used to mean absolute silence, and a customer trying to buy
    something wrote three times into a chat nobody had picked up. The agent
    still does not serve them — but the number answers."""
    fake, wa, calls = wired
    await handlers.process_inbound(inbound("first", "wamid.A"), BUSINESS_ID)
    contact_id = fake.rows("contacts")[0]["id"]
    await db.contacts.set_takeover(BUSINESS_ID, contact_id, True, by="staff@kfood.lk")
    wa.texts.clear()
    calls.clear()

    await handlers.process_inbound(inbound("second", "wamid.B"), BUSINESS_ID)

    assert calls == [], "the agent must not run while a human has the chat"
    assert len(wa.texts) == 1
    assert "come back to you" in wa.texts[0][1]
    # The message is still stored, so staff see it in the dashboard.
    assert any(m["body"] == "second" for m in fake.rows("messages"))


async def test_the_takeover_reply_is_sent_only_once(wired):
    """Three messages in a row must not produce three apologies."""
    fake, wa, calls = wired
    await handlers.process_inbound(inbound("first", "wamid.A"), BUSINESS_ID)
    contact_id = fake.rows("contacts")[0]["id"]
    await db.contacts.set_takeover(BUSINESS_ID, contact_id, True, by="staff@kfood.lk")
    wa.texts.clear()
    calls.clear()

    await handlers.process_inbound(inbound("hello?", "wamid.B"), BUSINESS_ID)
    await handlers.process_inbound(inbound("please reply", "wamid.C"), BUSINESS_ID)
    await handlers.process_inbound(inbound("anyone there", "wamid.D"), BUSINESS_ID)

    assert len(wa.texts) == 1, "one acknowledgement per takeover, not one per message"
    assert calls == []


async def test_a_staff_reply_replaces_the_takeover_acknowledgement(wired):
    """If a person has already answered, the customer must not then be told
    that someone will get back to them."""
    fake, wa, calls = wired
    await handlers.process_inbound(inbound("first", "wamid.A"), BUSINESS_ID)
    contact = fake.rows("contacts")[0]
    await db.contacts.set_takeover(BUSINESS_ID, contact["id"], True, by="staff@kfood.lk")

    # A staff member types a reply in the dashboard.
    await db.messages.save(
        business_id=BUSINESS_ID,
        contact_id=str(contact["id"]),
        direction="out",
        sender="human",
        body="Hi, I am checking that for you now.",
    )
    wa.texts.clear()
    calls.clear()

    await handlers.process_inbound(inbound("thanks", "wamid.B"), BUSINESS_ID)

    assert wa.texts == [], "a person is already talking to them"
    assert calls == []


async def test_inbound_message_reopens_the_window_each_time(wired):
    fake, _, _ = wired

    await handlers.process_inbound(inbound("one", "wamid.1"), BUSINESS_ID)
    first = fake.rows("contacts")[0]["last_customer_message_at"]
    await handlers.process_inbound(inbound("two", "wamid.2"), BUSINESS_ID)
    second = fake.rows("contacts")[0]["last_customer_message_at"]

    assert second >= first
    assert fake.rows("contacts")[0]["unread_count"] == 2


async def test_photo_without_caption_still_reaches_the_agent(wired):
    """A bare photo used to mean a silent takeover and a canned "I can't open
    attachments" reply. Most of them are bank slips, so that answer dropped a
    paying customer mid-sale. The agent now handles it — it sees the
    attachment marked unreadable in its history and decides what it is."""
    fake, wa, calls = wired

    await handlers.process_inbound(inbound(None, "wamid.IMG", mtype="image"), BUSINESS_ID)

    assert calls == [""], "the agent runs; the photo itself is in its history"
    assert fake.rows("contacts")[0]["human_takeover"] is False
    assert wa.texts, "the customer gets a real answer, not silence"


async def test_sticker_is_ignored_quietly(wired):
    fake, wa, calls = wired

    await handlers.process_inbound(inbound(None, "wamid.STK", mtype="sticker"), BUSINESS_ID)

    assert calls == []
    assert wa.texts == []
    assert fake.rows("contacts")[0]["human_takeover"] is False


async def test_voice_note_is_transcribed_before_agent_runs(wired, monkeypatch):
    fake, wa, calls = wired
    wa.media_downloads["media-voice"] = DownloadedMedia(
        content=b"ogg bytes",
        mime_type="audio/ogg",
        filename="voice.ogg",
    )

    async def transcribe(media):
        assert media.filename == "voice.ogg"
        return "Shin Ramyun packets dekak ona"

    monkeypatch.setattr(handlers, "transcribe_audio", transcribe)

    await handlers.process_inbound(
        inbound(
            None,
            "wamid.VOICE",
            mtype="voice",
            media_id="media-voice",
            media_mime="audio/ogg",
        ),
        BUSINESS_ID,
    )

    assert calls == ["Shin Ramyun packets dekak ona"]
    assert wa.downloaded_media_ids == ["media-voice"]
    stored = next(m for m in fake.rows("messages") if m["direction"] == "in")
    assert stored["body"] == "Shin Ramyun packets dekak ona"
    assert stored["transcript"] == "Shin Ramyun packets dekak ona"
    assert stored["transcription_status"] == "completed"


async def test_voice_transcription_failure_keeps_message_and_replies(wired, monkeypatch):
    fake, wa, calls = wired
    wa.media_downloads["media-bad"] = DownloadedMedia(
        content=b"not useful",
        mime_type="audio/ogg",
        filename="voice.ogg",
    )

    async def fail(_media):
        raise RuntimeError("speech service unavailable")

    monkeypatch.setattr(handlers, "transcribe_audio", fail)

    await handlers.process_inbound(
        inbound(None, "wamid.BADVOICE", mtype="voice", media_id="media-bad"),
        BUSINESS_ID,
    )

    assert calls == [""]
    assert wa.texts, "the existing ask-to-type fallback should still answer"
    stored = next(m for m in fake.rows("messages") if m["direction"] == "in")
    assert stored["transcription_status"] == "failed"
    assert "RuntimeError" in stored["transcription_error"]


async def test_payment_report_creates_separate_receipt_record(wired, monkeypatch):
    fake, _, _ = wired
    order_id = "33333333-3333-3333-3333-333333333333"

    async def payment_agent(*, business_id, contact, incoming_text, business_name="K-Food"):
        return AgentReply(
            text="Thanks, I will check it and confirm shortly.",
            payment_reported=True,
            payment_order={"id": order_id, "order_number": 1001},
        )

    monkeypatch.setattr(handlers, "run_agent", payment_agent)

    await handlers.process_inbound(
        inbound(
            "payment done",
            "wamid.RECEIPT",
            mtype="image",
            media_id="media-receipt",
            media_mime="image/jpeg",
        ),
        BUSINESS_ID,
    )

    receipts = fake.rows("payment_receipts")
    assert len(receipts) == 1
    assert receipts[0]["order_id"] == order_id
    assert receipts[0]["whatsapp_media_id"] == "media-receipt"
    assert receipts[0]["media_mime_type"] == "image/jpeg"
    assert receipts[0]["review_status"] == "pending_review"
    inbound_row = next(m for m in fake.rows("messages") if m["direction"] == "in")
    assert receipts[0]["message_id"] == inbound_row["id"]


async def test_a_crash_inside_processing_never_escapes(wired, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr(handlers.db.contacts, "get_or_create", boom)

    # A raised exception here would make Meta retry the whole delivery.
    await handlers.process_inbound(inbound("hi", "wamid.X"), BUSINESS_ID)


async def test_status_receipt_updates_the_sent_message(wired):
    fake, _, _ = wired
    await handlers.process_inbound(inbound("hi", "wamid.1"), BUSINESS_ID)
    outbound_row = [m for m in fake.rows("messages") if m["direction"] == "out"][0]

    from whatsapp.parser import StatusUpdate

    await handlers.process_status(
        StatusUpdate(
            wa_message_id=outbound_row["wa_message_id"],
            status="read",
            recipient_id="94771234567",
            timestamp=datetime.now(timezone.utc),
        )
    )

    assert [m for m in fake.rows("messages") if m["direction"] == "out"][0]["status"] == "read"


async def test_escalation_from_the_agent_is_respected(wired, monkeypatch):
    fake, wa, _ = wired

    async def escalating_agent(*, business_id, contact, incoming_text, business_name="K-Food"):
        await db.contacts.set_takeover(business_id, str(contact["id"]), True, by="agent")
        return AgentReply(text="A team member will reply shortly.", escalated=True,
                          escalation_reason="refund request")

    monkeypatch.setattr(handlers, "run_agent", escalating_agent)

    await handlers.process_inbound(inbound("I want a refund", "wamid.R"), BUSINESS_ID)

    assert fake.rows("contacts")[0]["human_takeover"] is True
    assert wa.texts[0][1] == "A team member will reply shortly."
