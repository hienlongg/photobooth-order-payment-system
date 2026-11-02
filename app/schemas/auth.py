import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str  # User ID
    tenant_id: str  # Tenant ID
    role: str  # "admin", "operator", "customer"
    exp: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime.datetime
