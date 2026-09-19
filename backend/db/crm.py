"""CRM storage: the customer record staff edit, and the follow-ups they keep.

The arithmetic lives in `crm.py` at the backend root and knows nothing about
Supabase. This module only fetches and writes rows.

One shape to notice: `customers()` reads contacts and orders as two plain
queries and joins them in Python rather than asking PostgREST to embed or
aggregate. That is the same call `db.orders.list_for_pos` makes, for the same
reason — the test fake models neither embedding nor aggregation, so a query
written that way would pass its tests while returning nothing in production.
At a few hundred contacts and a few thousand orders the join costs nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import first, get_db, rows

log = logging.getLogger(__name__)

TASKS = "crm_tasks"

# Columns a staff member may change on a contact. Anything outside this set is
# either the agent's business (unread_count, takeover) or Meta's (wa_id), and a
# PATCH that reached them would let the dashboard rewrite the 24-hour window.
EDITABLE_CONTACT_FIELDS = frozenset(
    {
        "name",
        "email",
        "address",
        "city",
        "birthday",
        "language",
        "lifecycle",
        "owner",
        "source",
        "tags",
        "marketing_opt_in",
    }
)

PRIORITIES = ("low", "normal", "high")


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
async def contacts_page(
    business_id: str, *, limit: int = 500, search: str | None = None
) -> list[dict[str, Any]]:
    db = await get_db()
    query = db.table("contacts").select("*").eq("business_id", business_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.or_(f"name.ilike.{needle},wa_id.ilike.{needle}")
    res = await query.order("last_seen", desc=True).limit(limit).execute()
    return rows(res)


async def orders_for_contacts(
    business_id: str, contact_ids: list[str], *, limit: int = 4000
) -> dict[str, list[dict[str, Any]]]:
    """Every order belonging to these customers, bucketed by contact.

    `limit` is a guard rail, not a page size: if it ever truncates, the lifetime
    values shown are wrong rather than merely incomplete, so it is set far above
    anything this shop will reach and logged if it bites.
    """
    if not contact_ids:
        return {}

    db = await get_db()
    res = (
        await db.table("orders")
        .select("id,contact_id,status,total,subtotal,items,source,created_at")
        .eq("business_id", business_id)
        .in_("contact_id", contact_ids)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    found = rows(res)
    if len(found) >= limit:
        log.warning("orders_for_contacts hit its limit", extra={"limit": limit})

    bucketed: dict[str, list[dict[str, Any]]] = {}
    for order in found:
        bucketed.setdefault(str(order.get("contact_id")), []).append(order)
    return bucketed


async def all_orders(business_id: str, *, limit: int = 4000) -> list[dict[str, Any]]:
    """The whole order history, for shop-wide analytics."""
    db = await get_db()
    res = (
        await db.table("orders")
        .select("id,contact_id,status,total,subtotal,items,source,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return rows(res)


async def update_contact(
    business_id: str, contact_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    """Apply a staff edit, dropping anything they are not allowed to set."""
    allowed = {k: v for k, v in patch.items() if k in EDITABLE_CONTACT_FIELDS}
    if not allowed:
        return None

    db = await get_db()
    res = (
        await db.table("contacts")
        .update(allowed)
        .eq("business_id", business_id)
        .eq("id", contact_id)
        .execute()
    )
    updated = first(res)
    log.info("contact updated", extra={"contact_id": contact_id, "fields": sorted(allowed)})
    return updated


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
async def notes_for_contact(contact_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """The full note history, pinned first — unlike db.notes.recent, which the
    agent uses and which returns only the text."""
    db = await get_db()
    res = (
        await db.table("notes")
        .select("*")
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    found = rows(res)
    # Pinned first, newest first within each group. Done here rather than in the
    # query because PostgREST cannot order by two directions across a partition.
    pinned = [n for n in found if n.get("pinned")]
    rest = [n for n in found if not n.get("pinned")]
    pinned.sort(key=lambda n: str(n.get("created_at")), reverse=True)
    rest.sort(key=lambda n: str(n.get("created_at")), reverse=True)
    return pinned + rest


async def set_note_pinned(
    business_id: str, note_id: str, pinned: bool
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table("notes")
        .update({"pinned": pinned})
        .eq("business_id", business_id)
        .eq("id", note_id)
        .execute()
    )
    return first(res)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
async def create_task(
    *,
    business_id: str,
    title: str,
    contact_id: str | None = None,
    order_id: str | None = None,
    detail: str | None = None,
    due_at: str | None = None,
    priority: str = "normal",
    assigned_to: str | None = None,
    created_by: str = "staff",
) -> dict[str, Any]:
    if priority not in PRIORITIES:
        raise ValueError(f"unknown task priority: {priority}")
    clean = title.strip()
    if not clean:
        raise ValueError("a task needs a title")

    db = await get_db()
    res = (
        await db.table(TASKS)
        .insert(
            {
                "business_id": business_id,
                "contact_id": contact_id,
                "order_id": order_id,
                "title": clean,
                "detail": detail,
                "due_at": due_at,
                "priority": priority,
                "assigned_to": assigned_to,
                "created_by": created_by,
            }
        )
        .execute()
    )
    task = first(res)
    if task is None:
        raise RuntimeError("task insert returned no row")
    log.info("task created", extra={"task_id": task.get("id"), "contact_id": contact_id})
    return task


async def get_task(business_id: str, task_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TASKS)
        .select("*")
        .eq("business_id", business_id)
        .eq("id", task_id)
        .limit(1)
        .execute()
    )
    return first(res)


async def update_task(
    business_id: str, task_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table(TASKS)
        .update(patch)
        .eq("business_id", business_id)
        .eq("id", task_id)
        .execute()
    )
    return first(res)


async def set_task_done(
    business_id: str, task_id: str, done: bool, *, by: str
) -> dict[str, Any] | None:
    """done_at carries the state, so closing and reopening is one field.

    A separate boolean would eventually disagree with the timestamp, and then
    nobody could say whether the follow-up was made.
    """
    patch = (
        {"done_at": datetime.now(timezone.utc).isoformat(), "done_by": by}
        if done
        else {"done_at": None, "done_by": None}
    )
    return await update_task(business_id, task_id, patch)


async def list_tasks(
    business_id: str,
    *,
    contact_id: str | None = None,
    state: str = "open",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """`state` is one of open | done | all.

    Open tasks come back soonest-due first with undated ones last, because an
    undated task is a someday and a dated one is a promise. PostgREST sorts
    nulls first on an ascending order, so the ordering is finished here.
    """
    db = await get_db()
    query = db.table(TASKS).select("*").eq("business_id", business_id)
    if contact_id:
        query = query.eq("contact_id", contact_id)
    res = await query.order("created_at", desc=True).limit(limit).execute()
    found = rows(res)

    if state == "open":
        found = [task for task in found if not task.get("done_at")]
        found.sort(key=lambda t: (t.get("due_at") is None, str(t.get("due_at") or "")))
    elif state == "done":
        found = [task for task in found if task.get("done_at")]
        found.sort(key=lambda t: str(t.get("done_at") or ""), reverse=True)

    return found


async def tasks_for_contacts(
    business_id: str, contact_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Open tasks bucketed by customer, so a list can show a follow-up flag."""
    if not contact_ids:
        return {}

    db = await get_db()
    res = (
        await db.table(TASKS)
        .select("*")
        .eq("business_id", business_id)
        .in_("contact_id", contact_ids)
        .execute()
    )
    bucketed: dict[str, list[dict[str, Any]]] = {}
    for task in rows(res):
        if task.get("done_at"):
            continue
        bucketed.setdefault(str(task.get("contact_id")), []).append(task)
    return bucketed


# ---------------------------------------------------------------------------
# Invoices — the POS bills, for staff rather than for a device
# ---------------------------------------------------------------------------
async def list_invoices(
    business_id: str, *, mismatched_only: bool = False, limit: int = 100
) -> list[dict[str, Any]]:
    db = await get_db()
    query = db.table("order_invoices").select("*").eq("business_id", business_id)
    if mismatched_only:
        query = query.eq("mismatch", True)
    res = await query.order("printed_at", desc=True).limit(limit).execute()
    return rows(res)


async def get_invoice(business_id: str, invoice_id: str) -> dict[str, Any] | None:
    db = await get_db()
    res = (
        await db.table("order_invoices")
        .select("*")
        .eq("business_id", business_id)
        .eq("id", invoice_id)
        .limit(1)
        .execute()
    )
    return first(res)
