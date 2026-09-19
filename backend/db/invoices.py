"""Invoices: what the printed paper says.

An invoice row is evidence that a piece of paper exists and is in a customer's
parcel. It is kept apart from the order's own state because the two can
legitimately disagree: a POS that was offline printed from a stale catalogue,
and the price on that paper is what the customer was charged whatever the
catalogue says now.

So both sets of figures are stored side by side, a mismatch is flagged, and a
human decides. Nothing here silently corrects paper.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TABLE = "order_invoices"


async def get_by_bill_no(business_id: str, bill_no: str) -> dict[str, Any] | None:
    """The idempotency check. A replayed bill must find its own row here."""
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("business_id", business_id)
        .eq("bill_no", bill_no)
        .limit(1)
        .execute()
    )
    return first(res)


async def list_for_order(order_id: str) -> list[dict[str, Any]]:
    db = await get_db()
    res = (
        await db.table(TABLE)
        .select("*")
        .eq("order_id", order_id)
        .order("printed_at", desc=True)
        .execute()
    )
    return rows(res)


async def create(
    *,
    business_id: str,
    order_id: str,
    device_id: str,
    bill_no: str,
    printed_at: str,
    paper: dict[str, float],
    server: dict[str, float],
    mismatch: bool,
    mismatch_detail: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    created_by: str,
    payment_method: str | None = None,
    catalog_version: str | None = None,
) -> dict[str, Any] | None:
    """Record a printed bill.

    Returns None when this bill_no already exists — the unique index turns a
    replayed outbox entry into a no-op rather than a second invoice. Callers
    treat that as success, which is the whole point of the idempotency key.
    """
    db = await get_db()
    payload = {
        "business_id": business_id,
        "order_id": order_id,
        "device_id": device_id,
        "bill_no": bill_no,
        "printed_at": printed_at,
        "paper_subtotal": paper.get("subtotal", 0),
        "paper_discount": paper.get("discount", 0),
        "paper_tax": paper.get("tax", 0),
        "paper_delivery": paper.get("delivery", 0),
        "paper_total": paper.get("total", 0),
        "server_subtotal": server.get("subtotal", 0),
        "server_discount": server.get("discount", 0),
        "server_tax": server.get("tax", 0),
        "server_delivery": server.get("delivery", 0),
        "server_total": server.get("total", 0),
        "mismatch": mismatch,
        "mismatch_detail": mismatch_detail,
        "lines": lines,
        "created_by": created_by,
        "payment_method": payment_method,
        "catalog_version": catalog_version,
    }

    try:
        res = await db.table(TABLE).insert(payload).execute()
    except Exception as exc:
        # The unique (business_id, bill_no) index fired: the same bill reached
        # us twice. Re-read rather than fail, exactly as contacts.get_or_create
        # does for a raced webhook delivery.
        log.info(
            "invoice insert raced, re-reading",
            extra={"bill_no": bill_no, "error": str(exc)},
        )
        return None

    created = first(res)
    if created:
        log.info(
            "invoice recorded",
            extra={
                "bill_no": bill_no,
                "order_id": order_id,
                "mismatch": mismatch,
                "device_id": device_id,
            },
        )
    return created


async def mark_reviewed(
    business_id: str, invoice_id: str, *, reviewed_by: str
) -> dict[str, Any] | None:
    """A human has looked at a price mismatch and decided."""
    from datetime import datetime, timezone

    db = await get_db()
    res = (
        await db.table(TABLE)
        .update(
            {
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "reviewed_by": reviewed_by,
            }
        )
        .eq("business_id", business_id)
        .eq("id", invoice_id)
        .execute()
    )
    return first(res)
