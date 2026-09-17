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
