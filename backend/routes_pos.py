"""The POS API.

K FOOD is online only: every order arrives through WhatsApp, and the POS prints
the invoice that goes in the courier parcel. So this is not a till API. It reads
the catalogue, reads orders the agent already created, and records bills.

Two rules shape everything here:

  * **It never touches stock.** Printing paper is not what takes a pack off the
    shelf; confirming the order is, and that already happens in the dashboard.
  * **It never trusts a total.** The POS sends SKUs and quantities; `pricing.py`
    prices them from the catalogue. A stale cache on the shop Mac cannot move
    money.

Every route is mounted behind `require_device`, which reads `X-Device-Token`.
Because the staff routes read `Authorization`, a device can never reach them —
it cannot message a customer, change an order's status, or move stock.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import catalog
import db
import pricing
import schemas
from auth import Device, require_device
from config import settings
from phones import InvalidPhone, to_local, to_wa_id
from ratelimit import RateLimiter

log = logging.getLogger(__name__)

pos = APIRouter(prefix="/pos", tags=["pos"], dependencies=[Depends(require_device)])

bill_limiter = RateLimiter(settings.pos_rate_limit_per_minute)

BUSINESS_ID = settings.business_id

# Which orders are worth printing. A delivered or cancelled order is history.
PRINTABLE_STATUSES = ("new", "confirmed", "preparing", "dispatched")


def _bill_no_pattern(device_id: str) -> re.Pattern[str]:
    """KF-<DEVICE>-YYYYMMDD-NNN, and the device must be this one.

    The device prefix is what stops two shop Macs both issuing -001 on the same
    day. Checking it here stops one device claiming another's numbering, which
    would let it overwrite the other's idempotency keys.
    """
    return re.compile(rf"^KF-{re.escape(device_id)}-\d{{8}}-\d{{3}}$")


def _contact_out(contact: dict[str, Any] | None) -> schemas.PosContact | None:
    if not contact:
        return None
    wa_id = str(contact.get("wa_id") or "")
    return schemas.PosContact(
        contact_id=str(contact.get("id")),
        name=contact.get("name"),
        wa_id=wa_id,
        display_phone=to_local(wa_id),
    )


def _order_out(order: dict[str, Any], invoices: list[dict[str, Any]] | None = None):
    return schemas.PosOrder(
        id=str(order.get("id")),
        order_number=order.get("order_number"),
        status=str(order.get("status") or "new"),
        created_at=str(order.get("created_at") or "") or None,
        items=list(order.get("items") or []),
        subtotal=float(order.get("subtotal") or 0),
        discount=float(order.get("discount") or 0),
        delivery_fee=float(order.get("delivery_fee") or 0),
        total=float(order.get("total") or 0),
        notes=order.get("notes"),
        customer=_contact_out(order.get("contact")),
        invoices=[
            {"bill_no": i.get("bill_no"), "printed_at": i.get("printed_at"),
             "mismatch": i.get("mismatch")}
            for i in (invoices or [])
        ],
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
@pos.get("/catalog", response_model=schemas.PosCatalogResponse)
async def pos_catalog(response: Response):
    """The catalogue with stock. The POS caches this and revalidates by ETag."""
    payload, version = await catalog.pos_catalog(BUSINESS_ID)
    response.headers["ETag"] = f'"{version}"'
    # The device holds its own copy in localStorage and decides when to refresh;
    # an intermediary caching this would only make its staleness harder to see.
    response.headers["Cache-Control"] = "no-cache"
    return payload


# ---------------------------------------------------------------------------
# Orders the agent already created
# ---------------------------------------------------------------------------
@pos.get("/orders", response_model=schemas.PosOrderListResponse)
async def list_orders(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Open orders with the customer attached, ready to print."""
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else list(
        PRINTABLE_STATUSES
    )
    orders = await db.orders.list_for_pos(BUSINESS_ID, statuses=statuses, limit=limit)
    return schemas.PosOrderListResponse(orders=[_order_out(o) for o in orders])


@pos.get("/orders/{order_id}", response_model=schemas.PosOrder)
async def get_order(order_id: str):
    order = await db.orders.get(BUSINESS_ID, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    order["contact"] = await db.contacts.get_by_id(BUSINESS_ID, str(order["contact_id"]))
    invoices = await db.invoices.list_for_order(order_id)
    return _order_out(order, invoices)


@pos.get("/contacts/lookup", response_model=schemas.PosContactLookupResponse)
async def lookup_contact(phone: str):
    """Resolve a phone number to a customer. Read-only — never creates.

    Staff type a number to see whether this customer already exists and whether
    they have an order open. Creating a contact here would litter the dashboard
    inbox with chats that never happened; creation belongs to a real bill.
    """
    try:
        wa_id = to_wa_id(phone)
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    contact = await db.contacts.get_by_wa_id(BUSINESS_ID, wa_id)
    if contact is None:
        return schemas.PosContactLookupResponse(found=False)

    open_order = await db.orders.open_for_contact(BUSINESS_ID, str(contact["id"]))
    return schemas.PosContactLookupResponse(
        found=True, contact=_contact_out(contact), open_order=open_order
    )


# ---------------------------------------------------------------------------
# Bills — the only write
# ---------------------------------------------------------------------------
@pos.post("/bills", response_model=schemas.PosBillResponse)
async def record_bill(
    payload: schemas.PosBillRequest,
    device: Device = Depends(require_device),
):
    """Record a printed bill, creating the order if one does not exist yet.

    One endpoint rather than two, because the POS syncs offline work from a
    queue: one queued job must be one request, or a retry has to remember which
    half already succeeded.
    """
    bill_limiter.check(device.device_id)

    if not _bill_no_pattern(device.device_id).match(payload.bill_no):
        raise HTTPException(
            status_code=422,
            detail=f"bill number must look like KF-{device.device_id}-YYYYMMDD-NNN",
        )

    # Idempotency, before anything is written. A replayed outbox entry finds its
    # own invoice and changes nothing — which the POS treats as success.
    existing = await db.invoices.get_by_bill_no(BUSINESS_ID, payload.bill_no)
    if existing is not None:
        order = await db.orders.get(BUSINESS_ID, str(existing["order_id"]))
        log.info("duplicate bill ignored", extra={"bill_no": payload.bill_no})
        return schemas.PosBillResponse(
            ok=True,
            duplicate=True,
            bill_no=payload.bill_no,
            order=order or {},
            invoice=existing,
            matches=not existing.get("mismatch"),
            differences=list(existing.get("mismatch_detail") or []),
        )

    try:
        wa_id = to_wa_id(payload.customer.phone)
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    contact = await db.contacts.get_or_create(BUSINESS_ID, wa_id, name=payload.customer.name)

    priced = await pricing.reprice(
        business_id=BUSINESS_ID,
        lines=payload.lines,
        printed_discount=payload.printed_totals.discount,
        delivery_override=payload.delivery_override,
    )

    paper = payload.printed_totals.model_dump()
    server = priced.totals()
    differences = list(priced.differences)
    totals_difference = pricing.compare_totals(paper, server)
    if totals_difference is not None:
        differences.append(totals_difference)

    order = await _resolve_order(payload, contact, priced, differences)

    invoice = await db.invoices.create(
        business_id=BUSINESS_ID,
        order_id=str(order["id"]),
        device_id=device.device_id,
        bill_no=payload.bill_no,
        printed_at=payload.printed_at.isoformat(),
        paper=paper,
        server=server,
        mismatch=bool(differences),
        mismatch_detail=[d.as_dict() for d in differences],
        lines=priced.items,
        created_by=device.label,
        payment_method=payload.payment_method,
        catalog_version=payload.catalog_version,
    )

    if invoice is None:
        # The unique index fired: the same bill reached us twice at once. Re-read
        # and answer as a duplicate, exactly as if we had seen it above.
        invoice = await db.invoices.get_by_bill_no(BUSINESS_ID, payload.bill_no) or {}
        return schemas.PosBillResponse(
            ok=True, duplicate=True, bill_no=payload.bill_no,
            order=order, invoice=invoice,
            matches=not invoice.get("mismatch"),
            differences=list(invoice.get("mismatch_detail") or []),
        )

    if differences:
        # Put it where staff will actually read it, in words and in rupees.
        await db.orders.append_note(
            BUSINESS_ID,
            str(order["id"]),
            f"POS bill {payload.bill_no} printed Rs. {paper.get('total', 0):,.0f}; "
            f"catalogue says Rs. {server['total']:,.0f}. Needs review.",
        )
        log.warning(
            "bill does not match the catalogue",
            extra={"bill_no": payload.bill_no, "order_id": str(order["id"]),
                   "printed_total": paper.get("total"), "server_total": server["total"],
                   "differences": len(differences)},
        )

    # Note what did NOT happen: no sell_order, no status change, no movement.
    # Stock still moves only at PATCH /orders/{id}/status -> confirmed.
    return schemas.PosBillResponse(
        ok=True,
        duplicate=False,
        bill_no=payload.bill_no,
        order=order,
        invoice=invoice,
        matches=not differences,
        differences=[d.as_dict() for d in differences],
    )


async def _resolve_order(
    payload: schemas.PosBillRequest,
    contact: dict[str, Any],
    priced: pricing.Repriced,
    differences: list[pricing.Difference],
) -> dict[str, Any]:
    """Find the order this bill belongs to, or create it.

    Both cases are real: the agent creates an order during a WhatsApp chat, and
    staff who took the chat over agree one by hand with nothing recorded.
    """
    if payload.order_id:
        order = await db.orders.get(BUSINESS_ID, payload.order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        if str(order.get("contact_id")) != str(contact["id"]):
            # A bill printed against another customer's order is a real error,
            # not something to reconcile quietly.
            raise HTTPException(
                status_code=422,
                detail="this order belongs to a different customer",
            )
        # Deliberately NOT rewritten. The agent priced this order and quoted it
        # to the customer on WhatsApp; the invoice records what the paper said,
        # and any difference is surfaced rather than applied.
        return order

    address = (payload.customer.address or "").strip()
    note = (payload.notes or "").strip()
    combined = "\n".join(part for part in (address, note) if part) or None

    return await db.orders.create(
        business_id=BUSINESS_ID,
        contact_id=str(contact["id"]),
        items=priced.items,
        subtotal=priced.subtotal,
        delivery_fee=priced.delivery,
        discount=priced.discount,
        discount_note=payload.discount_note,
        total=priced.total,
        notes=combined,
        source="pos",
        external_ref=payload.bill_no,
    )
