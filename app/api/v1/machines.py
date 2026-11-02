import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.machine import Machine
from app.models.user import User
from app.schemas.machine import MachineResponse, PaginatedMachineResponse

router = APIRouter(prefix="/machines", tags=["Machines"])


@router.get("", response_model=PaginatedMachineResponse)
async def list_machines(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (max 100)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedMachineResponse:
    """
    Retrieve a paginated list of machines for the caller's tenant.
    Requires an authenticated user (any role).
    """
    # 1. Base query scoped to the user's tenant
    base_filter = Machine.tenant_id == current_user.tenant_id

    # 2. Count total matching items
    count_query = select(func.count(Machine.id)).where(base_filter)
    total_count = (await db.execute(count_query)).scalar() or 0

    # 3. Calculate offset and query page items with deterministic sorting
    offset = (page - 1) * page_size
    items_query = (
        select(Machine)
        .where(base_filter)
        .order_by(Machine.created_at.desc(), Machine.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_result = await db.execute(items_query)
    machines = items_result.scalars().all()

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    return PaginatedMachineResponse(
        items=[MachineResponse.model_validate(m) for m in machines],
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
