import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    random_str = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )
    return f"ORD-{random_str}"


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "operator"])),
) -> OrderResponse:
    """
    Create a new photobooth order.
    - Strictly scoped to caller's tenant.
    - Validates machine is active and online.
    - Validates package is active.
    - Anti-tampering: enforces server-authoritative pricing from package.price_vnd.
    - Resilient: handles order_code collision with automatic retries.
    """
    # 1. Tenant status check
    if not current_user.tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is deactivated",
        )

    # 2. Machine validation
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
    if not machine.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Machine is deactivated",
        )
    if machine.status != "online":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Machine cannot accept orders (current status: '{machine.status}')",
        )

    # 3. Package validation
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
    if not package.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Package is archived or inactive",
        )

    # 4. Anti-tampering price verification (Server is sole price authority)
    if payload.amount_vnd is not None and payload.amount_vnd != package.price_vnd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Price mismatch: submitted {payload.amount_vnd} VND, but package price is {package.price_vnd} VND",
        )

    # 5. Order insertion with collision retry on unique order_code
    max_retries = 3
    new_order = None

    for attempt in range(max_retries):
        order_candidate = Order(
            tenant_id=current_user.tenant_id,
            machine_id=machine.id,
            package_id=package.id,
            order_code=generate_order_code(),
            amount_vnd=package.price_vnd,
            status="pending",
            payment_method=payload.payment_method,
        )
        try:
            async with db.begin_nested():
                db.add(order_candidate)
                await db.flush()
            new_order = order_candidate
            break
        except IntegrityError:
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate a unique order code. Please retry.",
                )

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
