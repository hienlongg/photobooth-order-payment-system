import datetime
from uuid import UUID
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class MachineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    machine_code: str
    name: str
    location: str | None = None
    status: str
    is_active: bool
    created_at: datetime.datetime


class PaginatedMachineResponse(BaseModel):
    items: List[MachineResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
