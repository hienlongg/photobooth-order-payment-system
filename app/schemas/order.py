import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderCreateRequest(BaseModel):
    machine_id: UUID
    package_id: UUID
    amount_vnd: int | None = Field(
        default=None,
        gt=0,
        description="Optional expected amount in VND. If provided, server verifies it matches package price.",
    )
    payment_method: str = Field(default="qr_pay", max_length=50)

    @field_validator("amount_vnd")
    @classmethod
    def validate_amount_vnd(cls, v: int | None) -> int | None:
        if v is not None:
            if v <= 0:
                raise ValueError("amount_vnd must be strictly greater than 0")
            if v > 100_000_000:
                raise ValueError(
                    "amount_vnd exceeds the single transaction limit of 100,000,000 VND"
                )
        return v


class OrderStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="Target order status: 'completed' or 'cancelled'",
        examples=["completed"],
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("completed", "cancelled"):
            raise ValueError("status must be either 'completed' or 'cancelled'")
        return v


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    machine_id: UUID
    package_id: UUID
    order_code: str
    amount_vnd: int
    status: str
    payment_method: str
    created_at: datetime.datetime


class PaginatedOrderResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
