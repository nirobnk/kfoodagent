"""Message log. Every inbound and outbound message lands here exactly once."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "messages"
MEDIA_BUCKET = "message-media"
MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    # What staff can send from the dashboard, kept so the chat shows it.
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


async def exists(wa_message_id: str) -> bool:
    db = await get_db()
    res = await db.table(TABLE).select("id").eq("wa_message_id", wa_message_id).limit(1).execute()
    return bool(rows(res))


async def save(
    *,
    business_id: str,
    contact_id: str,
    direction: str,
    sender: str,
    body: str | None = None,
    media_url: str | None = None,
    message_type: str = "text",
    template_name: str | None = None,
    wa_message_id: str | None = None,
    status: str = "sent",
    error: str | None = None,
    transcript: str | None = None,
    transcription_status: str | None = None,
    transcription_error: str | None = None,
    image_analysis_status: str | None = None,
    created_at: datetime | None = None,
    media_mime: str | None = None,
    media_filename: str | None = None,
    reply_to_wa_message_id: str | None = None,
    reply_to_text: str | None = None,
    reacted_to_wa_message_id: str | None = None,
    forwarded: bool = False,
) -> dict[str, Any] | None:
    """Insert a message.

    Idempotent on `wa_message_id`: Meta retries webhook deliveries, so the same
    inbound message arrives more than once. The unique index is the guard and
    this returns None when the row was already there.
    """
    payload: dict[str, Any] = {
        "business_id": business_id,
        "contact_id": contact_id,
        "direction": direction,
        "sender": sender,
        "body": body,
        "media_url": media_url,
        "message_type": message_type,
        "template_name": template_name,
        "wa_message_id": wa_message_id,
        "status": status,
        "error": error,
        "transcript": transcript,
        "transcription_status": transcription_status,
        "transcription_error": transcription_error,
        "image_analysis_status": image_analysis_status,
    }
    if created_at is not None:
        payload["created_at"] = created_at.astimezone(timezone.utc).isoformat()
    # Only what is set, so a plain text message reads the same as it always
    # has to a database that has not had migration 0018 yet.
    extras = {
        "media_mime": media_mime,
        "media_filename": media_filename,
        "reply_to_wa_message_id": reply_to_wa_message_id,
        "reply_to_text": reply_to_text,
        "reacted_to_wa_message_id": reacted_to_wa_message_id,
        "forwarded": forwarded or None,
    }
    payload.update({key: value for key, value in extras.items() if value})

    db = await get_db()

    if wa_message_id:
        res = (
            await db.table(TABLE)
            .upsert(payload, on_conflict="wa_message_id", ignore_duplicates=True)
            .execute()
        )
        saved = first(res)
        if saved is None:
            log.info("duplicate message ignored", extra={"wa_message_id": wa_message_id})
        return saved

    res = await db.table(TABLE).insert(payload).execute()
    return first(res)


async def complete_transcription(message_id: str, transcript: str) -> None:
    """Persist the readable voice-note text on its source message."""
    clean = transcript.strip()
    if not clean:
        raise ValueError("transcript cannot be empty")
    db = await get_db()
    await (
        db.table(TABLE)
        .update(
            {
                # Keeping body readable means existing dashboard clients show
                # the result without needing a coordinated frontend release.
                "body": clean,
                "transcript": clean,
                "transcription_status": "completed",
                "transcription_error": None,
            }
        )
        .eq("id", message_id)
        .execute()
    )


async def fail_transcription(message_id: str, error: str) -> None:
    """Record a safe diagnostic while leaving the original message intact."""
    db = await get_db()
    await (
        db.table(TABLE)
        .update(
            {
                "transcription_status": "failed",
                "transcription_error": (error or "voice transcription failed")[:500],
            }
        )
        .eq("id", message_id)
        .execute()
    )


async def complete_image_analysis(message_id: str, description: str) -> None:
    """Persist what the photo shows. The caption in `body` is left as written."""
    clean = description.strip()
    if not clean:
        raise ValueError("image description cannot be empty")
    db = await get_db()
    await (
        db.table(TABLE)
        .update(
            {
                "image_description": clean,
                "image_analysis_status": "completed",
                "image_analysis_error": None,
            }
        )
        .eq("id", message_id)
        .execute()
    )


async def fail_image_analysis(message_id: str, error: str) -> None:
    """Record a safe diagnostic while leaving the original message intact."""
    db = await get_db()
    await (
        db.table(TABLE)
        .update(
            {
                "image_analysis_status": "failed",
                "image_analysis_error": (error or "image analysis failed")[:500],
            }
        )
        .eq("id", message_id)
        .execute()
    )


async def store_media(
    *,
    message_id: str,
    business_id: str,
    contact_id: str,
    content: bytes,
    mime_type: str,
    filename: str | None = None,
) -> None:
    """Copy a message's photo or file into private storage and point the message at it.

    Everything customers send — photos, stickers, voice notes, videos,
    documents — and the photos and files staff send.
    """
    clean_mime = mime_type.split(";", 1)[0].strip().lower() or "application/octet-stream"
    extension = MEDIA_EXTENSIONS.get(clean_mime) or _extension_from(filename)
    if not content:
        raise ValueError("message media is empty")

    digest = hashlib.sha256(content).hexdigest()
    path = f"{business_id}/{contact_id}/{message_id}/{digest}{extension}"
    db = await get_db()
    await db.storage.from_(MEDIA_BUCKET).upload(
        path=path,
        file=content,
        file_options={
            "content-type": clean_mime,
            "cache-control": "3600",
            # The path is content-addressed, so retries are safe.
            "upsert": "true",
        },
    )
    patch: dict[str, Any] = {"media_path": path}
    try:
        await db.table(TABLE).update(
            patch | {"media_mime": clean_mime, "media_size": len(content)}
            | ({"media_filename": filename} if filename else {})
        ).eq("id", message_id).execute()
    except Exception:
        # A database without migration 0018 still gets the path.
        await db.table(TABLE).update(patch).eq("id", message_id).execute()


def _extension_from(filename: str | None) -> str:
    """".pdf" from "receipt.pdf"; ".bin" when the name says nothing usable."""
    name = (filename or "").rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext.isalnum() and len(ext) <= 8:
            return f".{ext}"
    return ".bin"


async def get(business_id: str, message_id: str) -> dict[str, Any] | None:
    """One message of this shop's, by our own id: what staff reply to or react to."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id,contact_id,direction,sender,body,message_type,media_filename,wa_message_id")
        .eq("business_id", business_id)
        .eq("id", message_id)
        .limit(1)
        .execute()
    )
    return first(res)


async def get_by_wa_id(wa_message_id: str) -> dict[str, Any] | None:
    """One message by Meta's id: what a reply quotes, or a reaction points at."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id,direction,sender,body,message_type,media_filename,contact_id")
        .eq("wa_message_id", wa_message_id)
        .limit(1)
        .execute()
    )
    return first(res)


def snippet(row: dict[str, Any] | None, limit: int = 160) -> str | None:
    """How a quoted message reads in one line, the way WhatsApp shows it."""
    if not row:
        return None
    body = " ".join(str(row.get("body") or "").split())
    if not body or body.startswith("["):
        body = {
            "image": "📷 Photo", "sticker": "Sticker", "video": "🎥 Video",
            "audio": "🎤 Voice message", "voice": "🎤 Voice message",
            "document": f"📄 {row.get('media_filename') or 'Document'}",
        }.get(str(row.get("message_type")), body or "Message")
    return body[:limit] + ("…" if len(body) > limit else "")


async def signed_media_url(
    business_id: str, message_id: str, *, expires_in: int = 300
) -> str | None:
    """A short-lived URL for one stored inbound photo, or None if there is none."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("media_path")
        .eq("business_id", business_id)
        .eq("id", message_id)
        .limit(1)
        .execute()
    )
    path = (first(res) or {}).get("media_path")
    if not path:
        return None
    signed = await db.storage.from_(MEDIA_BUCKET).create_signed_url(str(path), expires_in)
    return str(signed.get("signedUrl") or signed.get("signedURL") or "") or None


async def update_status(wa_message_id: str, status: str, error: str | None = None) -> None:
    """Apply a delivery receipt. Never downgrades read -> delivered -> sent."""
    rank = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id,status")
        .eq("wa_message_id", wa_message_id)
        .limit(1)
        .execute()
    )
    row = first(res)
    if row is None:
        return
    if rank.get(status, 0) <= rank.get(row.get("status") or "sent", 1) and status != "failed":
        return

    patch: dict[str, Any] = {"status": status}
    if error:
        patch["error"] = error
    await db.table(TABLE).update(patch).eq("id", row["id"]).execute()


async def history(contact_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Last `limit` messages, oldest first — the shape the agent wants."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select(
            "direction,sender,body,message_type,transcript,transcription_status,"
            "image_description,image_analysis_status,created_at,"
            "media_filename,media_mime,reply_to_text,forwarded"
        )
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(rows(res)))


async def list_for_contact(
    contact_id: str, limit: int = 200, before: str | None = None
) -> list[dict[str, Any]]:
    db = await get_db()
    query = db.table(TABLE).select("*").eq("contact_id", contact_id)
    if before:
        query = query.lt("created_at", before)
    res = await query.order("created_at", desc=True).limit(limit).execute()
    return list(reversed(rows(res)))


async def any_outbound_since(contact_id: str, since: str) -> bool:
    """Has anything gone out to this customer since `since`?

    Used to answer "has this chat been silent since a person took it over?"
    without adding a column to track it: a staff reply, a template, or an
    earlier acknowledgement all count, so the customer is reassured exactly
    once and never talked over.
    """
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id")
        .eq("contact_id", contact_id)
        .eq("direction", "out")
        .gte("created_at", since)
        .limit(1)
        .execute()
    )
    return bool(rows(res))


async def count_since(business_id: str, since: datetime, direction: str = "out") -> int:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("id", count="exact")
        .eq("business_id", business_id)
        .eq("direction", direction)
        .gte("created_at", since.astimezone(timezone.utc).isoformat())
        .limit(1)
        .execute()
    )
    return int(res.count or 0)
