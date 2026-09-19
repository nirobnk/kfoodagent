"""The CRM API.

The rest of this backend answers "what happened". These routes answer "who is
this customer, and what should someone do about them next" — the questions the
dashboard's CRM asks.

Every route is mounted behind `require_staff`, which reads `Authorization`. A
POS device sends `X-Device-Token` and so can never reach any of it: the shop Mac
must not be able to read the customer book, and the boundary is structural
rather than a matter of remembering to check.

What this does NOT do:

  * It never sends a message. Messaging stays on `/messages/*`, where the
    WhatsApp token, the 24-hour window check and the message log all live.
  * It never moves stock or changes an order's status. Those have owners
    already, and a second path to them is a second place for them to go wrong.
  * It stores no derived totals. Lifetime value, segment and the rest are
    computed from `orders` on every read by `crm.py`, so a figure on screen can
    always be traced back to the orders behind it.

`GET /crm/invoices` closes the gap Phase 2 left open: `order_invoices` was
reachable only by the device that wrote it, so a printed bill with a price
mismatch had nowhere to be reviewed. It is a read plus one review action, which
is what that gap actually needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

import crm
import db
import schemas
from auth import Principal, require_staff
from config import settings
from whatsapp import window

log = logging.getLogger(__name__)

crm_api = APIRouter(prefix="/crm", tags=["crm"], dependencies=[Depends(require_staff)])

BUSINESS_ID = settings.business_id

# How much history the customer list reads. Above this the page stops being a
# list and needs a search, which is what the `search` parameter is for.
CUSTOMER_PAGE = 500


async def _contact_or_404(contact_id: str) -> dict[str, Any]:
    contact = await db.contacts.get_by_id(BUSINESS_ID, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return contact


def _sent(patch: Any) -> dict[str, Any]:
    """Only the fields the caller actually sent.

    Pydantic fills the rest with None, and writing those would clear a name
    somebody else typed a second earlier.
    """
    return patch.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@crm_api.get("/customers", response_model=schemas.CustomerListResponse)
async def list_customers(
    search: str | None = Query(default=None, max_length=120),
    lifecycle: str | None = Query(default=None),
    limit: int = Query(default=CUSTOMER_PAGE, le=CUSTOMER_PAGE),
    staff: Principal = Depends(require_staff),
) -> schemas.CustomerListResponse:
    """The customer book, each row carrying what its orders say about it."""
    contacts = await db.crm.contacts_page(BUSINESS_ID, limit=limit, search=search)
    if lifecycle:
        contacts = [c for c in contacts if c.get("lifecycle") == lifecycle]

    contact_ids = [str(c["id"]) for c in contacts]
    orders = await db.crm.orders_for_contacts(BUSINESS_ID, contact_ids)
    tasks = await db.crm.tasks_for_contacts(BUSINESS_ID, contact_ids)

    now = datetime.now(timezone.utc)
    customers: list[schemas.CustomerSummary] = []
    segments: dict[str, int] = {}

    for contact in contacts:
        contact_id = str(contact["id"])
        stats = crm.summarise(orders.get(contact_id, []), now=now)
        open_tasks = tasks.get(contact_id, [])
        due = sorted(t["due_at"] for t in open_tasks if t.get("due_at"))

        # The stage on the record wins. The suggestion travels with the stats so
        # the dashboard can offer it, and staff can see when the two disagree.
        stage = str(contact.get("lifecycle") or "lead")
        segments[stage] = segments.get(stage, 0) + 1

        customers.append(
            schemas.CustomerSummary(
                contact=contact,
                stats=stats.as_dict(),
                open_tasks=len(open_tasks),
                next_due_at=due[0] if due else None,
            )
        )

    return schemas.CustomerListResponse(customers=customers, segments=segments)


@crm_api.get("/customers/{contact_id}", response_model=schemas.CustomerDetailResponse)
async def customer_detail(
    contact_id: str, staff: Principal = Depends(require_staff)
) -> schemas.CustomerDetailResponse:
    """Everything about one customer, on one screen."""
    contact = await _contact_or_404(contact_id)

    orders = (await db.crm.orders_for_contacts(BUSINESS_ID, [contact_id])).get(contact_id, [])
    notes = await db.crm.notes_for_contact(contact_id)
    tasks = await db.crm.list_tasks(BUSINESS_ID, contact_id=contact_id, state="all")
    messages = await db.messages.list_for_contact(contact_id, limit=20)

    invoices: list[dict[str, Any]] = []
    for order in orders[:20]:
        invoices.extend(await db.invoices.list_for_order(str(order["id"])))

    remaining = window.window_remaining(contact)
    return schemas.CustomerDetailResponse(
        contact=contact,
        stats=crm.summarise(orders).as_dict(),
        orders=orders,
        notes=notes,
        tasks=tasks,
        invoices=invoices,
        messages=messages,
        window_open=window.can_send_free_text(contact),
        window_remaining_human=window.format_remaining(remaining),
    )


@crm_api.patch("/customers/{contact_id}", response_model=schemas.ContactResponse)
async def update_customer(
    contact_id: str,
    payload: schemas.CustomerPatch,
    staff: Principal = Depends(require_staff),
) -> schemas.ContactResponse:
    """Save a staff edit. Only the fields sent are written."""
    await _contact_or_404(contact_id)

    patch = _sent(payload)
    if not patch:
        raise HTTPException(status_code=400, detail="nothing to update")

    updated = await db.crm.update_contact(BUSINESS_ID, contact_id, patch)
    if updated is None:
        raise HTTPException(status_code=400, detail="no editable fields in that update")

    log.info(
        "customer updated",
        extra={"contact_id": contact_id, "staff": staff.label, "fields": sorted(patch)},
    )
    return schemas.ContactResponse(contact=updated)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
@crm_api.post("/customers/{contact_id}/notes", response_model=schemas.NoteResponse)
async def add_note(
    contact_id: str,
    payload: schemas.NoteRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.NoteResponse:
    """Write a note against a customer.

    `created_by` is the staff member's label rather than 'agent', which is what
    the agent's own notes carry. The agent reads this table when it answers, so
    a note typed here changes what the customer is told next time.
    """
    await _contact_or_404(contact_id)

    note = await db.notes.add(
        business_id=BUSINESS_ID,
        contact_id=contact_id,
        note=payload.note,
        created_by=staff.label,
    )
    if note is None:
        raise HTTPException(status_code=500, detail="note not saved")

    if payload.pinned:
        note = await db.crm.set_note_pinned(BUSINESS_ID, str(note["id"]), True) or note

    return schemas.NoteResponse(note=note)


@crm_api.patch("/notes/{note_id}", response_model=schemas.NoteResponse)
async def pin_note(
    note_id: str,
    payload: schemas.NotePinRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.NoteResponse:
    note = await db.crm.set_note_pinned(BUSINESS_ID, note_id, payload.pinned)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    return schemas.NoteResponse(note=note)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@crm_api.get("/tasks", response_model=schemas.TaskListResponse)
async def list_tasks(
    state: str = Query(default="open", pattern="^(open|done|all)$"),
    contact_id: str | None = None,
    limit: int = Query(default=200, le=500),
    staff: Principal = Depends(require_staff),
) -> schemas.TaskListResponse:
    tasks = await db.crm.list_tasks(
        BUSINESS_ID, contact_id=contact_id, state=state, limit=limit
    )

    now = datetime.now(timezone.utc).isoformat()
    open_tasks = [task for task in tasks if not task.get("done_at")]
    overdue = [t for t in open_tasks if t.get("due_at") and str(t["due_at"]) < now]

    return schemas.TaskListResponse(
        tasks=tasks, open_count=len(open_tasks), overdue_count=len(overdue)
    )


@crm_api.post("/tasks", response_model=schemas.TaskResponse)
async def create_task(
    payload: schemas.TaskRequest, staff: Principal = Depends(require_staff)
) -> schemas.TaskResponse:
    if payload.contact_id:
        await _contact_or_404(payload.contact_id)

    try:
        task = await db.crm.create_task(
            business_id=BUSINESS_ID,
            title=payload.title,
            contact_id=payload.contact_id,
            order_id=payload.order_id,
            detail=payload.detail,
            due_at=payload.due_at,
            priority=payload.priority,
            assigned_to=payload.assigned_to or staff.label,
            created_by=staff.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return schemas.TaskResponse(task=task)


@crm_api.patch("/tasks/{task_id}", response_model=schemas.TaskResponse)
async def update_task(
    task_id: str,
    payload: schemas.TaskPatch,
    staff: Principal = Depends(require_staff),
) -> schemas.TaskResponse:
    """Edit a follow-up, or tick it off.

    `done` is not a column: it sets `done_at`, which is the state. Sending
    `done: false` reopens the task and clears who closed it.
    """
    existing = await db.crm.get_task(BUSINESS_ID, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="task not found")

    patch = _sent(payload)
    done = patch.pop("done", None)

    if patch.get("priority") and patch["priority"] not in db.crm.PRIORITIES:
        raise HTTPException(status_code=400, detail="unknown task priority")

    task = existing
    if patch:
        task = await db.crm.update_task(BUSINESS_ID, task_id, patch) or task
    if done is not None:
        task = await db.crm.set_task_done(BUSINESS_ID, task_id, done, by=staff.label) or task

    return schemas.TaskResponse(task=task)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@crm_api.get("/analytics", response_model=schemas.AnalyticsResponse)
async def analytics(
    days: int = Query(default=30, ge=7, le=365),
    staff: Principal = Depends(require_staff),
) -> schemas.AnalyticsResponse:
    """Shop-wide figures, all derived from the orders themselves.

    The whole history is read, not only the window: "new customer" means a first
    order ever, and judging that against a 30-day slice would make every
    returning customer look new.
    """
    now = datetime.now(timezone.utc)
    orders = await db.crm.all_orders(BUSINESS_ID)
    contacts = await db.crm.contacts_page(BUSINESS_ID, limit=CUSTOMER_PAGE)

    in_window = crm.within(orders, days=days, now=now)

    segments: dict[str, int] = {}
    for contact in contacts:
        stage = str(contact.get("lifecycle") or "lead")
        segments[stage] = segments.get(stage, 0) + 1

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return schemas.AnalyticsResponse(
        days=days,
        totals=crm.totals(orders, days=days, now=now),
        revenue_by_day=crm.revenue_by_day(orders, days=days, now=now),
        top_products=crm.top_products(in_window),
        status_mix=crm.mix(in_window, "status"),
        source_mix=crm.mix(in_window, "source"),
        acquisition=crm.new_versus_returning(orders, days=days, now=now),
        segments=segments,
        messages={
            "month_start": month_start.date().isoformat(),
            "outbound": await db.messages.count_since(BUSINESS_ID, month_start, direction="out"),
            "inbound": await db.messages.count_since(BUSINESS_ID, month_start, direction="in"),
        },
    )


# ---------------------------------------------------------------------------
# Invoices — the printed bills, and the mismatches waiting on a human
# ---------------------------------------------------------------------------
@crm_api.get("/invoices", response_model=schemas.InvoiceListResponse)
async def list_invoices(
    mismatched_only: bool = False,
    limit: int = Query(default=100, le=200),
    staff: Principal = Depends(require_staff),
) -> schemas.InvoiceListResponse:
    invoices = await db.crm.list_invoices(
        BUSINESS_ID, mismatched_only=mismatched_only, limit=limit
    )
    unreviewed = [
        invoice
        for invoice in invoices
        if invoice.get("mismatch") and not invoice.get("reviewed_at")
    ]
    return schemas.InvoiceListResponse(invoices=invoices, mismatch_count=len(unreviewed))


@crm_api.post("/invoices/{invoice_id}/review", response_model=schemas.InvoiceReviewResponse)
async def review_invoice(
    invoice_id: str, staff: Principal = Depends(require_staff)
) -> schemas.InvoiceReviewResponse:
    """A human has looked at a price mismatch and decided.

    This records that they looked. It deliberately does not correct anything:
    the paper in the customer's parcel says what it says, and rewriting the
    figures here would hide the one piece of evidence about what was charged.
    """
    existing = await db.crm.get_invoice(BUSINESS_ID, invoice_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="invoice not found")

    invoice = await db.invoices.mark_reviewed(BUSINESS_ID, invoice_id, reviewed_by=staff.label)
    if invoice is None:
        raise HTTPException(status_code=500, detail="review not saved")

    log.info("invoice reviewed", extra={"invoice_id": invoice_id, "staff": staff.label})
    return schemas.InvoiceReviewResponse(invoice=invoice)
