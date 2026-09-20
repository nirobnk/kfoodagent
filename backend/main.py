"""FastAPI application: WhatsApp webhook + the staff API the dashboard calls."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

import db
import jobs
import outbound
import routes_crm
import routes_pos
import routes_public
import schemas
from auth import Principal, require_staff
from config import settings
from handlers import process_inbound, process_status
from logging_config import setup_logging
from ratelimit import RateLimiter
from whatsapp import parse_webhook, verify_signature, window
from whatsapp.client import close_client

setup_logging(settings.log_level, json_output=settings.is_production)
log = logging.getLogger("kfood.api")

send_limiter = RateLimiter(settings.send_rate_limit_per_minute)
BUSINESS_ID = settings.business_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    warnings = settings.check_production_readiness()
    for warning in warnings:
        log.warning("startup check: %s", warning)
    if settings.is_production and warnings:
        raise RuntimeError(
            "refusing to start in production with unresolved security warnings: "
            + "; ".join(warnings)
        )

    try:
        await db.ping()
        log.info("database reachable")
    except Exception:
        log.exception("database unreachable at startup")
        if settings.is_production:
            raise

    stop = asyncio.Event()
    task = asyncio.create_task(jobs.auto_return_loop(stop))
    app.state.stop_event = stop
    app.state.jobs = task

    yield

    stop.set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    await close_client()
    await db.close_db()


app = FastAPI(
    title="K-Food WhatsApp Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    # ngrok-skip-browser-warning: while the API is exposed through a free ngrok
    # tunnel, browser requests are answered with ngrok's interstitial HTML page
    # instead of the API. That header opts out of it, so the preflight has to
    # allow it. Harmless once the backend has a real domain.
    #
    # X-Device-Token: the POS's credential. A separate header from Authorization
    # on purpose — see auth.py.
    # If-None-Match: the catalogue and availability routes are the only cacheable
    # ones, and conditional requests are how a device revalidates 90 products in
    # a few bytes.
    allow_headers=[
        "Authorization",
        "Content-Type",
        "ngrok-skip-browser-warning",
        "X-Device-Token",
        "If-None-Match",
    ],
    # Without this the browser can receive an ETag but not read it, so every
    # conditional fetch silently degrades into a full one and nobody notices.
    expose_headers=["ETag"],
)

# Public catalogue for kfoods.lk, the POS behind its device token, and the CRM
# behind staff auth. Routers rather than routes here, so each one's auth tier is
# declared once instead of on every path.
app.include_router(routes_public.public)
app.include_router(routes_pos.pos)
app.include_router(routes_crm.crm_api)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", response_model=schemas.HealthResponse)
async def health() -> schemas.HealthResponse:
    try:
        await db.ping()
        database = "ok"
    except Exception as exc:
        log.error("health check: database unreachable", extra={"error": str(exc)})
        database = "unreachable"

    return schemas.HealthResponse(
        status="ok" if database == "ok" else "degraded",
        environment=settings.environment,
        database=database,
        whatsapp_configured=bool(
            settings.wa_access_token.get_secret_value() and settings.wa_phone_number_id
        ),
        warnings=settings.check_production_readiness(),
    )


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "kfood-whatsapp-agent", "status": "ok"}


# ---------------------------------------------------------------------------
# WhatsApp webhook
# ---------------------------------------------------------------------------
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request) -> PlainTextResponse:
    """Meta's subscription handshake. The challenge goes back as plain text."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token == settings.wa_verify_token.get_secret_value():
        log.info("webhook verified by Meta")
        return PlainTextResponse(challenge, status_code=200)

    log.warning("webhook verification failed", extra={"mode": mode})
    raise HTTPException(status_code=403, detail="verification failed")


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    """Answer Meta in milliseconds, then do the real work in the background.

    Meta retries anything slower than a few seconds, and a retry means a
    duplicate reply to the customer.
    """
    raw = await request.body()

    if not verify_signature(settings.wa_app_secret.get_secret_value(), raw, x_hub_signature_256):
        log.warning("webhook signature rejected")
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        payload = await request.json()
    except Exception:
        log.warning("webhook body was not json")
        return JSONResponse({"status": "ignored"}, status_code=200)

    parsed = parse_webhook(payload)
    if parsed.is_empty:
        return JSONResponse({"status": "ignored"}, status_code=200)

    for message in parsed.messages:
        background.add_task(process_inbound, message, BUSINESS_ID)
    for update in parsed.statuses:
        background.add_task(process_status, update)

    return JSONResponse(
        {"status": "accepted", "messages": len(parsed.messages), "statuses": len(parsed.statuses)},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Staff API — everything below requires a signed-in staff member
# ---------------------------------------------------------------------------
async def _contact_or_404(contact_id: str) -> dict[str, Any]:
    contact = await db.contacts.get_by_id(BUSINESS_ID, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return contact


@app.post("/messages/send", response_model=schemas.SendMessageResponse)
async def send_message(
    payload: schemas.SendMessageRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.SendMessageResponse:
    send_limiter.check(staff.user_id)
    contact = await _contact_or_404(payload.contact_id)

    if payload.take_over and not contact.get("human_takeover"):
        contact = (
            await db.contacts.set_takeover(BUSINESS_ID, contact["id"], True, by=staff.label)
            or contact
        )

    result = await outbound.send_text(
        business_id=BUSINESS_ID, contact=contact, body=payload.body, sender="human"
    )
    log.info(
        "staff message",
        extra={"staff": staff.label, "contact_id": contact["id"], "ok": result.ok,
               "reason": result.reason},
    )
    return schemas.SendMessageResponse(
        ok=result.ok, wa_message_id=result.wa_message_id, reason=result.reason
    )


@app.post("/messages/send-template", response_model=schemas.SendMessageResponse)
async def send_template_message(
    payload: schemas.SendTemplateRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.SendMessageResponse:
    send_limiter.check(staff.user_id)
    contact = await _contact_or_404(payload.contact_id)

    if payload.take_over and not contact.get("human_takeover"):
        contact = (
            await db.contacts.set_takeover(BUSINESS_ID, contact["id"], True, by=staff.label)
            or contact
        )

    result = await outbound.send_template(
        business_id=BUSINESS_ID,
        contact=contact,
        key=payload.template_key,
        variables=payload.variables,
        sender="human",
    )
    return schemas.SendMessageResponse(
        ok=result.ok,
        wa_message_id=result.wa_message_id,
        template_name=result.template_name,
        reason=result.reason,
    )


@app.post("/contacts/{contact_id}/takeover", response_model=schemas.ContactResponse)
async def set_takeover(
    contact_id: str,
    payload: schemas.TakeoverRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.ContactResponse:
    await _contact_or_404(contact_id)
    contact = await db.contacts.set_takeover(
        BUSINESS_ID, contact_id, payload.enabled, by=staff.label
    )
    return schemas.ContactResponse(contact=contact or {})


@app.post("/contacts/{contact_id}/read", response_model=schemas.ContactResponse)
async def mark_read(
    contact_id: str, staff: Principal = Depends(require_staff)
) -> schemas.ContactResponse:
    await _contact_or_404(contact_id)
    contact = await db.contacts.mark_read(BUSINESS_ID, contact_id)
    return schemas.ContactResponse(contact=contact or {})


@app.get("/contacts/{contact_id}/window", response_model=schemas.WindowResponse)
async def get_window(
    contact_id: str, staff: Principal = Depends(require_staff)
) -> schemas.WindowResponse:
    contact = await _contact_or_404(contact_id)
    remaining = window.window_remaining(contact)
    expires = window.window_expires_at(contact)
    return schemas.WindowResponse(
        open=window.can_send_free_text(contact),
        expires_at=expires.isoformat() if expires else None,
        remaining_seconds=int(remaining.total_seconds()),
        remaining_human=window.format_remaining(remaining),
    )


@app.get("/templates")
async def list_templates(staff: Principal = Depends(require_staff)) -> dict[str, Any]:
    return {"templates": await db.templates.list_all(BUSINESS_ID)}


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderStatusResponse)
async def update_order_status(
    order_id: str,
    payload: schemas.OrderStatusRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.OrderStatusResponse:
    existing = await db.orders.get(BUSINESS_ID, order_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="order not found")

    order = await db.orders.set_status(BUSINESS_ID, order_id, payload.status)
    if order is None:
        raise HTTPException(status_code=500, detail="status update failed")

    # Stock follows the order, not the other way round: confirming an order is
    # what sells it, cancelling is what puts it back. Both are idempotent, so a
    # status flipped back and forth cannot sell or invent stock twice. Untracked
    # products are skipped, so this is a no-op until staff turn tracking on.
    stock_changed: list[str] = []
    if existing.get("status") != payload.status:
        if payload.status == "confirmed":
            stock_changed = await db.inventory.sell_order(order, created_by=staff.label)
        elif payload.status == "cancelled":
            stock_changed = await db.inventory.restock_order(order, created_by=staff.label)

    notified = False
    reason: str | None = None
    if payload.notify and existing.get("status") != payload.status:
        contact = await db.contacts.get_by_id(BUSINESS_ID, str(order["contact_id"]))
        if contact is None:
            reason = "contact_missing"
        else:
            result = await outbound.notify_order_status(
                business_id=BUSINESS_ID, order=order, contact=contact, status=payload.status
            )
            notified = result.ok
            reason = result.reason
    elif not payload.notify:
        reason = "notify_disabled"
    else:
        reason = "status_unchanged"

    log.info(
        "order status updated",
        extra={"order_id": order_id, "status": payload.status, "staff": staff.label,
               "notified": notified, "reason": reason, "stock_changed": len(stock_changed)},
    )
    return schemas.OrderStatusResponse(order=order, notified=notified, notify_reason=reason)


@app.patch("/orders/{order_id}/payment", response_model=schemas.PaymentStatusResponse)
async def update_order_payment(
    order_id: str,
    payload: schemas.PaymentStatusRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.PaymentStatusResponse:
    """Mark an order paid, unpaid or refunded.

    Only a person can say the money arrived. The agent records that a slip was
    sent; confirming it against the account is this endpoint, and the note
    keeps whoever checked it on the record.
    """
    existing = await db.orders.get(BUSINESS_ID, order_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="order not found")

    note = (payload.note or "").strip()
    line = f"{payload.payment_status} by {staff.label}" + (f" — {note}" if note else "")
    order = await db.orders.set_payment_status(
        BUSINESS_ID, order_id, payload.payment_status, note=line
    )
    if order is None:
        raise HTTPException(status_code=500, detail="payment update failed")

    log.info(
        "order payment updated",
        extra={"order_id": order_id, "payment_status": payload.payment_status,
               "staff": staff.label},
    )
    return schemas.PaymentStatusResponse(order=order)


@app.get("/orders")
async def list_orders(
    status: str | None = None,
    limit: int = 100,
    staff: Principal = Depends(require_staff),
) -> dict[str, Any]:
    statuses = [s.strip() for s in status.split(",")] if status else None
    orders = await db.orders.list_for_business(
        BUSINESS_ID, statuses=statuses, limit=min(limit, 200)
    )
    return {"orders": orders}


@app.get("/contacts")
async def list_contacts(
    limit: int = 100, staff: Principal = Depends(require_staff)
) -> dict[str, Any]:
    return {"contacts": await db.contacts.list_recent(BUSINESS_ID, limit=min(limit, 200))}


@app.get("/stats/usage", response_model=schemas.UsageResponse)
async def usage(staff: Principal = Depends(require_staff)) -> schemas.UsageResponse:
    """Monthly message counter.

    From 1 October 2026 Meta charges for service messages and utility templates
    sent inside the 24-hour window, with the first 1,000 service messages per
    number per month free. Staff need to see the number climbing.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sent = await db.messages.count_since(BUSINESS_ID, month_start, direction="out")
    received = await db.messages.count_since(BUSINESS_ID, month_start, direction="in")
    return schemas.UsageResponse(
        month_start=month_start.date().isoformat(),
        outbound_messages=sent,
        inbound_messages=received,
        free_service_messages_remaining=max(0, 1000 - sent),
    )


# ---------------------------------------------------------------------------
# Inventory — stock as a ledger, so a wrong number can always be explained
# ---------------------------------------------------------------------------
@app.get("/inventory", response_model=schemas.StockLevelsResponse)
async def stock_levels(
    tracked_only: bool = False, staff: Principal = Depends(require_staff)
) -> schemas.StockLevelsResponse:
    items = await db.inventory.levels(BUSINESS_ID, tracked_only=tracked_only)
    return schemas.StockLevelsResponse(items=items)


@app.get("/inventory/movements", response_model=schemas.StockMovementsResponse)
async def stock_movements(
    menu_item_id: str | None = None,
    limit: int = 50,
    staff: Principal = Depends(require_staff),
) -> schemas.StockMovementsResponse:
    """The ledger behind the numbers, newest first."""
    movements = await db.inventory.movements(
        BUSINESS_ID, menu_item_id=menu_item_id, limit=min(limit, 200)
    )
    return schemas.StockMovementsResponse(movements=movements)


@app.post("/inventory/movements", response_model=schemas.StockChangeResponse)
async def record_stock_movement(
    payload: schemas.StockMovementRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.StockChangeResponse:
    """Record a delivery, a breakage, a correction."""
    movement = await db.inventory.record(
        business_id=BUSINESS_ID,
        menu_item_id=payload.menu_item_id,
        delta=payload.delta,
        reason=payload.reason,
        note=payload.note,
        created_by=staff.label,
    )
    quantity = await db.inventory.quantity(BUSINESS_ID, payload.menu_item_id)
    log.info(
        "stock movement recorded",
        extra={"staff": staff.label, "menu_item_id": payload.menu_item_id,
               "delta": payload.delta, "reason": payload.reason, "on_hand": quantity},
    )
    return schemas.StockChangeResponse(
        ok=movement is not None,
        menu_item_id=payload.menu_item_id,
        stock_quantity=quantity,
        movement=movement,
    )


@app.post("/inventory/count", response_model=schemas.StockChangeResponse)
async def record_stock_count(
    payload: schemas.StockCountRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.StockChangeResponse:
    """A stocktake. Stored as the difference, so the ledger keeps its history."""
    movement = await db.inventory.set_count(
        business_id=BUSINESS_ID,
        menu_item_id=payload.menu_item_id,
        counted=payload.counted,
        created_by=staff.label,
        note=payload.note,
    )
    quantity = await db.inventory.quantity(BUSINESS_ID, payload.menu_item_id)
    return schemas.StockChangeResponse(
        ok=True,
        menu_item_id=payload.menu_item_id,
        stock_quantity=quantity,
        movement=movement,
        # A count that matches records nothing, and staff should see that
        # rather than wonder why the ledger did not grow.
        reason=None if movement else "already_correct",
    )


@app.patch("/inventory/tracking", response_model=schemas.StockChangeResponse)
async def set_stock_tracking(
    payload: schemas.StockTrackingRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.StockChangeResponse:
    """Turn stock tracking on or off for one SKU.

    Off means unlimited, which is how every product behaved before stock
    existed. Turn it on only after the first count, or the agent will believe
    there are zero of something the shelf is full of.
    """
    item = await db.inventory.set_tracking(
        BUSINESS_ID, payload.menu_item_id, payload.track_stock
    )
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    log.info(
        "stock tracking changed",
        extra={"staff": staff.label, "menu_item_id": payload.menu_item_id,
               "track_stock": payload.track_stock},
    )
    return schemas.StockChangeResponse(
        ok=True,
        menu_item_id=payload.menu_item_id,
        stock_quantity=int(item.get("stock_quantity") or 0),
    )


# ---------------------------------------------------------------------------
# Devices — the POS terminals, administered by staff
# ---------------------------------------------------------------------------
@app.get("/devices", response_model=schemas.DeviceListResponse)
async def list_devices(
    staff: Principal = Depends(require_staff),
) -> schemas.DeviceListResponse:
    """Every till, live or revoked. The token hash never leaves the backend."""
    return schemas.DeviceListResponse(devices=await db.devices.list_for_business(BUSINESS_ID))


@app.post("/devices", response_model=schemas.DeviceCreateResponse)
async def create_device(
    payload: schemas.DeviceCreateRequest,
    staff: Principal = Depends(require_staff),
) -> schemas.DeviceCreateResponse:
    """Mint a device token.

    The raw token is returned exactly once, here. Only its hash is stored, so a
    lost token cannot be recovered — it is revoked and a new one is minted.
    """
    device, raw = await db.devices.create(
        business_id=BUSINESS_ID,
        device_id=payload.device_id,
        name=payload.name,
        created_by=staff.label,
    )
    log.info(
        "device token created",
        extra={"device_id": device.get("device_id"), "staff": staff.label},
    )
    return schemas.DeviceCreateResponse(device=device, token=raw)


@app.post("/devices/{token_id}/revoke")
async def revoke_device(
    token_id: str, staff: Principal = Depends(require_staff)
) -> dict[str, Any]:
    """Make a lost shop Mac useless. POST, because CORS allows no DELETE."""
    device = await db.devices.revoke(BUSINESS_ID, token_id, revoked_by=staff.label)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    return {"ok": True, "device": device}


@app.post("/inventory/recompute")
async def recompute_stock(staff: Principal = Depends(require_staff)) -> dict[str, Any]:
    """Rebuild every cached quantity from the ledger.

    The whole point of keeping movements is that the number can be re-derived.
    Run this when the shelf and the screen disagree.
    """
    corrected = await db.inventory.recompute(BUSINESS_ID)
    log.info("stock recomputed", extra={"staff": staff.label, "corrected": corrected})
    return {"ok": True, "rows_corrected": corrected}
