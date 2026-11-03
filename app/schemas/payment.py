import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreateRequest(BaseModel):
    provider: str = Field(default="fake_payos", max_length=50)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    provider: str
    payment_reference: str
    order_code: str
    amount_vnd: int
    status: str
    checkout_url: str | None = None
    qr_code: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    bin: str | None = None
    expires_at: datetime.datetime | None = None
    created_at: datetime.datetime


class WebhookEventResponse(BaseModel):
    status: str
    message: str
    order_id: UUID | None = None
    order_status: str | None = None
    is_duplicate: bool = False


class PaymentEventBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    amount_vnd: int
    status: str
    is_valid_signature: bool
    created_at: datetime.datetime


class OrderPaymentStatusResponse(BaseModel):
    order_id: UUID
    order_code: str
    order_status: str
    amount_vnd: int
    is_paid: bool
    payment_method: str
    paid_at: datetime.datetime | None = None
    expires_at: datetime.datetime | None = None
    latest_payment: PaymentResponse | None = None
    events_count: int = 0
    events: list[PaymentEventBrief] = []
