"""Payment-receipt evidence and its independent review lifecycle."""

from __future__ import annotations

from typing import Any

from .client import first, get_db, rows

TABLE = "payment_receipts"
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
