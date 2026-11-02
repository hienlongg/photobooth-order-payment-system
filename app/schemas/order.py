import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderCreateRequest(BaseModel):
    machine_id: UUID
    package_id: UUID
    amount_vnd: int = Field(
        ...,
        gt=0,
        description="Transaction amount in Vietnamese Dong, must be greater than 0"
    )
    payment_method: str = Field(default="qr_pay", max_length=50)

    @field_validator("amount_vnd")
    @classmethod
    def validate_amount_vnd(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount_vnd must be strictly greater than 0")
        if v > 100_000_000:
            raise ValueError("amount_vnd exceeds the single transaction limit of 100,000,000 VND")
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
