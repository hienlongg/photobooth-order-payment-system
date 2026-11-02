import secrets
import string
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.machine import Machine
from app.models.order import Order
from app.models.package import Package
from app.models.user import User
from app.schemas.order import OrderCreateRequest, OrderResponse

router = APIRouter(prefix="/orders", tags=["Orders"])


def generate_order_code() -> str:
    """Generates an 8-character unique alphanumeric order code (e.g., ORD-7K9W2B1X)."""
    random_str = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"ORD-{random_str}"


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreateRequest,
    db: AsyncSession = Depends(get_db),
    # Both 'admin' and 'operator' can create orders; 'customer' role is restricted
    current_user: User = Depends(require_role(["admin", "operator"])),
) -> OrderResponse:
    """
    Create a new photobooth order.
    Validates machine and package existence, verifies tenant ownership,
    and returns 201 Created.
    """
    # 1. Validate machine exists and belongs to this tenant
    m_res = await db.execute(
        select(Machine).where(
            Machine.id == payload.machine_id,
            Machine.tenant_id == current_user.tenant_id,
        )
    )
    machine = m_res.scalar_one_or_none()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {payload.machine_id} not found in this tenant",
        )

    # 2. Validate package exists and belongs to this tenant
    p_res = await db.execute(
        select(Package).where(
            Package.id == payload.package_id,
            Package.tenant_id == current_user.tenant_id,
        )
    )
    package = p_res.scalar_one_or_none()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Package {payload.package_id} not found in this tenant",
        )

    # 3. Create Order
    new_order = Order(
        tenant_id=current_user.tenant_id,
        machine_id=machine.id,
        package_id=package.id,
        order_code=generate_order_code(),
        amount_vnd=payload.amount_vnd,
        status="pending",
        payment_method=payload.payment_method,
    )
    db.add(new_order)
    await db.flush()  # Flushes to DB to obtain default IDs and server-side fields
    await db.refresh(new_order)

    return OrderResponse.model_validate(new_order)


@router.get("/{id}", response_model=OrderResponse)
async def get_order_by_id(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    """
    Fetch an order by UUID.
    Restricted to orders belonging to the authenticated user's tenant.
    """
    result = await db.execute(
        select(Order).where(
            Order.id == id,
            Order.tenant_id == current_user.tenant_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {id} not found",
        )

    return OrderResponse.model_validate(order)
