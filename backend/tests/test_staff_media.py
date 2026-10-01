"""Staff sending photos, videos, audio and documents from the dashboard."""

from __future__ import annotations

import io

from PIL import Image

from tests.test_api import client, seeded_contact, wired  # noqa: F401 — fixtures

JPEG = b"\xff\xd8\xff\xe0 a tiny jpeg"


def webp_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(out, format="WEBP")
    return out.getvalue()


def send(client, contact_id, name, content, mime, caption="", take_over="true"):  # noqa: F811
    return client.post(
        "/messages/send-media",
        data={"contact_id": contact_id, "caption": caption, "take_over": take_over},
        files={"file": (name, content, mime)},
    )


def test_staff_can_send_a_photo_and_that_takes_over_the_chat(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "shin.jpg", JPEG, "image/jpeg", caption="Here it is")

    assert response.json()["ok"] is True
    assert wa.uploads == [(JPEG, "image/jpeg", "shin.jpg")]
    assert wa.media == [("94771234567", "image", "media-upload-1", "Here it is", "shin.jpg")]
    assert fake.rows("contacts")[0]["human_takeover"] is True
    [message] = fake.rows("messages")
    assert message["sender"] == "human"
    assert message["message_type"] == "image"
    assert message["body"] == "Here it is"
    assert message["media_path"].endswith(".jpg"), "a copy is kept for the dashboard"
    assert ("message-media", message["media_path"]) in fake.storage.files


def test_a_document_goes_with_its_file_name(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "invoice-23.pdf", b"%PDF-1.7 x", "application/pdf",
                    caption="Your invoice")

    assert response.json()["ok"] is True
    assert wa.media[0][1] == "document"
    assert wa.media[0][4] == "invoice-23.pdf"
    assert fake.rows("messages")[0]["body"] == "📄 invoice-23.pdf\nYour invoice"


def test_audio_and_video_are_sent_as_themselves(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    send(client, contact["id"], "note.m4a", b"audio", "audio/x-m4a")
    send(client, contact["id"], "unboxing.mp4", b"video", "video/mp4")

    assert [m[1] for m in wa.media] == ["audio", "video"]
    assert wa.uploads[0][1] == "audio/mp4", "an alias is sent as the type WhatsApp knows"
    assert [m["body"] for m in fake.rows("messages")] == ["[audio]", "[video]"]


def test_a_webp_photo_is_sent_as_a_jpeg(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "pack.webp", webp_bytes(), "image/webp")

    assert response.json()["ok"] is True
    content, mime, name = wa.uploads[0]
    assert mime == "image/jpeg" and name == "pack.jpg"
    assert content.startswith(b"\xff\xd8")


def test_a_file_whatsapp_refuses_is_refused_without_taking_over(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "clip.mov", b"mov", "video/quicktime")

    assert response.json()["reason"] == "unsupported_file"
    assert wa.media == []
    assert fake.rows("contacts")[0]["human_takeover"] is False


def test_a_photo_over_five_megabytes_is_refused(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "big.jpg", b"\xff" * (5 * 1024 * 1024 + 1), "image/jpeg")

    assert response.json()["reason"] == "file_too_large"
    assert wa.media == []


def test_media_is_refused_outside_the_window(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake, hours_ago=30)

    response = send(client, contact["id"], "shin.jpg", JPEG, "image/jpeg")

    assert response.json()["reason"] == "window_closed"
    assert wa.media == []


def test_a_type_is_worked_out_from_the_name_when_the_browser_gives_none(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)

    response = send(client, contact["id"], "menu.pdf", b"%PDF", "application/octet-stream")

    assert response.json()["ok"] is True
    assert wa.uploads[0][1] == "application/pdf"


def test_the_stored_copy_can_be_opened_from_the_dashboard(client, wired):  # noqa: F811
    fake, wa = wired
    contact = seeded_contact(fake)
    send(client, contact["id"], "shin.jpg", JPEG, "image/jpeg")
    message_id = fake.rows("messages")[0]["id"]

    response = client.get(f"/messages/{message_id}/media")

    assert response.status_code == 200
    assert response.json()["url"]
