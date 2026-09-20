"""Request and response models for the staff, public and POS APIs.

Public and POS responses are built from EXPLICIT models, never by handing a
database row to FastAPI. `menu_items` carries `stock_quantity` on every row, and
a dict passthrough would publish the shop's stock levels to anyone who curls the
catalogue. PostgREST column projection cannot be relied on to prevent that — the
test fake ignores projection, so such a leak would pass every test and ship.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    contact_id: str
    body: str = Field(min_length=1, max_length=4096)
    take_over: bool = Field(
        default=True,
        description="Switch the chat to human handling, so the agent stays quiet.",
    )


class SendTemplateRequest(BaseModel):
    contact_id: str
    template_key: str
    variables: list[str] = Field(default_factory=list)
    take_over: bool = True


class SendMessageResponse(BaseModel):
    ok: bool
    wa_message_id: str | None = None
    template_name: str | None = None
    reason: str | None = None


class TakeoverRequest(BaseModel):
    enabled: bool


class ContactResponse(BaseModel):
    contact: dict[str, Any]


class WindowResponse(BaseModel):
    open: bool
    expires_at: str | None
    remaining_seconds: int
    remaining_human: str


class OrderStatusRequest(BaseModel):
    status: Literal["new", "confirmed", "preparing", "dispatched", "delivered", "cancelled"]
    notify: bool = True


class OrderStatusResponse(BaseModel):
    order: dict[str, Any]
    notified: bool
    notify_reason: str | None = None


class PaymentStatusRequest(BaseModel):
    """Where an order stands on money, which staff own.

    The agent may only ever set 'receipt_received' — it records that a slip
    arrived, never that the money did. Moving an order to 'verified' means a
    person looked at the account, so it happens here and nowhere else.
    """

    payment_status: Literal["unpaid", "receipt_received", "verified", "refunded"]
    note: str | None = None


class PaymentStatusResponse(BaseModel):
    order: dict[str, Any]


class UsageResponse(BaseModel):
    month_start: str
    outbound_messages: int
    inbound_messages: int
    free_service_messages_remaining: int


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    whatsapp_configured: bool
    warnings: list[str] = Field(default_factory=list)


# --- inventory -------------------------------------------------------------

class StockMovementRequest(BaseModel):
    """One change to stock, recorded as a movement.

    'sold' is absent deliberately: a sale comes from confirming an order, never
    from someone typing it, or the ledger stops reconciling against orders.
    """

    menu_item_id: str
    reason: Literal["received", "returned", "damaged", "expired", "adjusted"]
    # Signed: +24 for a delivery, -3 for breakages. Zero changes nothing.
    delta: int = Field(..., ne=0)
    note: str | None = None


class StockCountRequest(BaseModel):
    """A stocktake: what is physically on the shelf right now."""

    menu_item_id: str
    counted: int = Field(..., ge=0)
    note: str | None = None


class StockTrackingRequest(BaseModel):
    menu_item_id: str
    track_stock: bool


class StockLevelsResponse(BaseModel):
    items: list[dict[str, Any]]


class StockMovementsResponse(BaseModel):
    movements: list[dict[str, Any]]


class StockChangeResponse(BaseModel):
    ok: bool
    menu_item_id: str
    stock_quantity: int
    movement: dict[str, Any] | None = None
    reason: str | None = None


# --- public catalogue ------------------------------------------------------
# Served unauthenticated to kfoods.lk. Every field here is already visible on
# the website; nothing about stock levels or customers appears.

class PublicVariant(BaseModel):
    sku: str
    label: str | None = None
    price: float
    units: int = 1


class PublicProduct(BaseModel):
    handle: str
    name: str
    ko: str | None = None
    brand: str | None = None
    category: str | None = None
    pack: str | None = None
    heat: int | None = None
    cook: str | None = None
    badge: str | None = None
    short: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    variants: list[PublicVariant] = Field(default_factory=list)


class PublicStore(BaseModel):
    """The facts the website currently hardcodes into its own markup."""

    name: str
    site: str | None = None
    currency: str = "LKR"
    whatsapp: str | None = None
    delivery_fee: float = 0
    free_delivery_threshold: float | None = None
    price_range: str | None = None
    bank: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)


class PublicCatalogResponse(BaseModel):
    generated_at: str
    version: str
    store: PublicStore
    categories: list[str] = Field(default_factory=list)
    products: list[PublicProduct] = Field(default_factory=list)


class AvailabilityItem(BaseModel):
    """Two states, never a number.

    An exact count tells a competitor the shop's sales volume. A boolean tells a
    customer what they need to know, which is the only thing this is for.
    """

    handle: str
    sku: str
    state: Literal["in_stock", "out_of_stock"]


class AvailabilityResponse(BaseModel):
    generated_at: str
    items: list[AvailabilityItem] = Field(default_factory=list)


# --- POS -------------------------------------------------------------------

class PosVariant(PublicVariant):
    """The POS sees stock; it is a staff tool behind a device token."""

    track_stock: bool = False
    stock_quantity: int = 0


class PosProduct(PublicProduct):
    variants: list[PosVariant] = Field(default_factory=list)
    track_stock: bool = False
    stock_quantity: int = 0


class PosCatalogResponse(BaseModel):
    generated_at: str
    version: str
    store: PublicStore
    categories: list[str] = Field(default_factory=list)
    products: list[PosProduct] = Field(default_factory=list)


class PosContact(BaseModel):
    contact_id: str
    name: str | None = None
    wa_id: str
    display_phone: str


class PosContactLookupResponse(BaseModel):
    found: bool
    contact: PosContact | None = None
    open_order: dict[str, Any] | None = None


class PosOrder(BaseModel):
    id: str
    order_number: int | None = None
    status: str
    created_at: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    subtotal: float = 0
    discount: float = 0
    delivery_fee: float = 0
    total: float = 0
    notes: str | None = None
    customer: PosContact | None = None
    invoices: list[dict[str, Any]] = Field(default_factory=list)


class PosOrderListResponse(BaseModel):
    orders: list[PosOrder] = Field(default_factory=list)


class PosBillLine(BaseModel):
    # Absent or "CUSTOM-*" means the catalogue has no entry and the printed
    # price is trusted, because there is no other source for it.
    sku: str | None = None
    name: str | None = None
    variant: str | None = None
    quantity: int = Field(default=1, ge=1, le=200)
    printed_unit_price: float = Field(default=0, ge=0, le=1_000_000)


class PosTotals(BaseModel):
    subtotal: float = 0
    discount: float = 0
    tax: float = 0
    delivery: float = 0
    total: float = 0


class PosCustomer(BaseModel):
    phone: str
    name: str | None = None
    address: str | None = None
    note: str | None = None


class PosBillRequest(BaseModel):
    """One printed bill. The bill number is the idempotency key."""

    bill_no: str = Field(min_length=6, max_length=64)
    printed_at: datetime
    # Set when the agent already created the order on WhatsApp; absent when
    # staff agreed the order by hand and the POS is recording it first.
    order_id: str | None = None
    customer: PosCustomer
    lines: list[PosBillLine] = Field(min_length=1)
    discount_note: str | None = None
    delivery_override: float | None = Field(default=None, ge=0)
    payment_method: str | None = None
    notes: str | None = None
    printed_totals: PosTotals
    catalog_version: str | None = None


class PosBillResponse(BaseModel):
    ok: bool
    # True when this bill_no was already recorded. The POS treats it as success:
    # it is the whole point of the idempotency key.
    duplicate: bool = False
    bill_no: str
    order: dict[str, Any] = Field(default_factory=dict)
    invoice: dict[str, Any] = Field(default_factory=dict)
    matches: bool = True
    differences: list[dict[str, Any]] = Field(default_factory=list)


# --- devices (staff-only administration) -----------------------------------

class DeviceCreateRequest(BaseModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9]{2,6}$")
    name: str = Field(min_length=1, max_length=120)


class DeviceCreateResponse(BaseModel):
    device: dict[str, Any]
    # Shown once and never retrievable again — only its hash is stored.
    token: str


class DeviceListResponse(BaseModel):
    devices: list[dict[str, Any]] = Field(default_factory=list)


# --- CRM (staff-only) -------------------------------------------------------

LIFECYCLE = Literal["lead", "active", "regular", "vip", "at_risk", "lost", "blocked"]
CONTACT_SOURCE = Literal["whatsapp", "pos", "web", "referral", "walk_in", "other"]


class CustomerPatch(BaseModel):
    """A staff edit to a customer record.

    Every field is optional and only the ones sent are written, so two people
    editing different halves of the same record do not overwrite each other.
    `db.crm.EDITABLE_CONTACT_FIELDS` is the second gate: a field that appears
    here but not there is silently dropped rather than trusted.
    """

    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    birthday: str | None = Field(default=None, description="ISO date, or null to clear")
    language: Literal["en", "si", "ta"] | None = None
    lifecycle: LIFECYCLE | None = None
    owner: str | None = Field(default=None, max_length=120)
    source: CONTACT_SOURCE | None = None
    tags: list[str] | None = None
    marketing_opt_in: bool | None = None


class CustomerSummary(BaseModel):
    """One row of the customer list: the contact, plus what its orders say."""

    contact: dict[str, Any]
    stats: dict[str, Any]
    open_tasks: int = 0
    next_due_at: str | None = None


class CustomerListResponse(BaseModel):
    customers: list[CustomerSummary] = Field(default_factory=list)
    segments: dict[str, int] = Field(default_factory=dict)


class CustomerDetailResponse(BaseModel):
    contact: dict[str, Any]
    stats: dict[str, Any]
    orders: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    window_open: bool = False
    window_remaining_human: str = "closed"


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    pinned: bool = False


class NotePinRequest(BaseModel):
    pinned: bool


class NoteResponse(BaseModel):
    note: dict[str, Any]


class TaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    contact_id: str | None = None
    order_id: str | None = None
    detail: str | None = Field(default=None, max_length=2000)
    due_at: str | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    assigned_to: str | None = Field(default=None, max_length=120)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)
    due_at: str | None = None
    priority: Literal["low", "normal", "high"] | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    done: bool | None = None


class TaskResponse(BaseModel):
    task: dict[str, Any]


class TaskListResponse(BaseModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    open_count: int = 0
    overdue_count: int = 0


class AnalyticsResponse(BaseModel):
    days: int
    totals: dict[str, Any]
    revenue_by_day: list[dict[str, Any]] = Field(default_factory=list)
    top_products: list[dict[str, Any]] = Field(default_factory=list)
    status_mix: list[dict[str, Any]] = Field(default_factory=list)
    source_mix: list[dict[str, Any]] = Field(default_factory=list)
    acquisition: dict[str, Any] = Field(default_factory=dict)
    segments: dict[str, int] = Field(default_factory=dict)
    messages: dict[str, Any] = Field(default_factory=dict)


class InvoiceListResponse(BaseModel):
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    mismatch_count: int = 0


class InvoiceReviewResponse(BaseModel):
    invoice: dict[str, Any]
