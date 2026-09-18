"""Request and response models for the staff API."""

from __future__ import annotations

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
