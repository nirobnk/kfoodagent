"""Payment-receipt evidence and its independent review lifecycle."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

TABLE = "payment_receipts"
BUCKET = "payment-receipts"
MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
REVIEW_STATUSES = {
    "pending_review",
    "details_match",
    "details_mismatch",
    "duplicate",
    "verified",
    "rejected",
}


async def create(
    *,
    business_id: str,
    contact_id: str,
    message_id: str | None = None,
    order_id: str | None = None,
    whatsapp_media_id: str | None = None,
    media_mime_type: str | None = None,
    private_media_path: str | None = None,
    file_sha256: str | None = None,
    reported_detail: str | None = None,
    storage_status: str = "not_applicable",
) -> dict[str, Any]:
    """Create one receipt record, idempotently when tied to a message."""
    payload = {
        "business_id": business_id,
        "contact_id": contact_id,
        "order_id": order_id,
        "message_id": message_id,
        "whatsapp_media_id": whatsapp_media_id,
        "media_mime_type": media_mime_type,
        "private_media_path": private_media_path,
        "file_sha256": file_sha256,
        "reported_detail": reported_detail,
        "storage_status": storage_status,
        "review_status": "pending_review",
    }
    database = await get_db()
    if message_id:
        result = await (
            database.table(TABLE)
            .upsert(payload, on_conflict="message_id", ignore_duplicates=True)
            .execute()
        )
        receipt = first(result)
        if receipt is None:
            receipt = await get_by_message(message_id)
    else:
        receipt = first(await database.table(TABLE).insert(payload).execute())
    if receipt is None:
        raise RuntimeError("payment receipt insert returned no row")
    return receipt


async def store_media(
    *,
    receipt_id: str,
    business_id: str,
    contact_id: str,
    content: bytes,
    mime_type: str,
) -> dict[str, Any] | None:
    """Upload receipt evidence privately, then attach its durable path."""
    clean_mime = mime_type.split(";", 1)[0].strip().lower()
    extension = MEDIA_EXTENSIONS.get(clean_mime)
    if extension is None:
        raise ValueError(f"unsupported receipt MIME type: {clean_mime}")
    if not content:
        raise ValueError("receipt file is empty")

    digest = hashlib.sha256(content).hexdigest()
    path = f"{business_id}/{contact_id}/{receipt_id}/{digest}{extension}"
    database = await get_db()
    await database.storage.from_(BUCKET).upload(
        path=path,
        file=content,
        file_options={
            "content-type": clean_mime,
            "cache-control": "3600",
            # The path is content-addressed, so retries are safe.
            "upsert": "true",
        },
    )
    result = await (
        database.table(TABLE)
        .update(
            {
                "private_media_path": path,
                "file_sha256": digest,
                "file_size_bytes": len(content),
                "media_mime_type": clean_mime,
                "storage_status": "stored",
                "storage_error": None,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("business_id", business_id)
        .eq("id", receipt_id)
        .execute()
    )
    return first(result)


async def mark_storage_failed(
    business_id: str, receipt_id: str, error: str
) -> dict[str, Any] | None:
    database = await get_db()
    result = await (
        database.table(TABLE)
        .update(
            {
                "storage_status": "failed",
                "storage_error": (error or "receipt storage failed")[:500],
            }
        )
        .eq("business_id", business_id)
        .eq("id", receipt_id)
        .execute()
    )
    return first(result)


async def signed_media_url(
    business_id: str, receipt_id: str, *, expires_in: int = 300
) -> str | None:
    """Return a short-lived URL for one staff-authorized receipt lookup."""
    database = await get_db()
    result = await (
        database.table(TABLE)
        .select("private_media_path,storage_status")
        .eq("business_id", business_id)
        .eq("id", receipt_id)
        .limit(1)
        .execute()
    )
    receipt = first(result)
    path = (receipt or {}).get("private_media_path")
    if not path or (receipt or {}).get("storage_status") != "stored":
        return None
    signed = await database.storage.from_(BUCKET).create_signed_url(
        str(path), expires_in
    )
    return str(signed.get("signedUrl") or signed.get("signedURL") or "") or None


async def get_by_message(message_id: str) -> dict[str, Any] | None:
    database = await get_db()
    result = await (
        database.table(TABLE)
        .select("*")
        .eq("message_id", message_id)
        .limit(1)
        .execute()
    )
    return first(result)


async def list_for_order(order_id: str) -> list[dict[str, Any]]:
    database = await get_db()
    result = await (
        database.table(TABLE)
        .select("*")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .execute()
    )
    return rows(result)


async def update_analysis(
    receipt_id: str,
    *,
    extracted_data: dict[str, Any],
    amount: float | None = None,
    bank_name: str | None = None,
    transaction_reference: str | None = None,
    confidence: float | None = None,
    review_status: str = "pending_review",
) -> dict[str, Any] | None:
    """Store machine-extracted fields without treating them as verification."""
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"unknown receipt review status: {review_status}")
    database = await get_db()
    result = await (
        database.table(TABLE)
        .update(
            {
                "extracted_data": extracted_data,
                "amount": amount,
                "bank_name": bank_name,
                "transaction_reference": transaction_reference,
                "analysis_confidence": confidence,
                "review_status": review_status,
            }
        )
        .eq("id", receipt_id)
        .execute()
    )
    return first(result)
