import datetime
import math
import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.config import settings
from app.db.session import get_db
from app.models.machine import Machine
from app.models.order import Order
from app.models.package import Package
from app.models.user import User
from app.schemas.order import (
    OrderCreateRequest,
    OrderResponse,
    OrderStatusUpdate,
    PaginatedOrderResponse,
)
from app.schemas.payment import (
    OrderPaymentStatusResponse,
    PaymentCreateRequest,
    PaymentResponse,
)
from app.services.payment.service import PaymentService
from app.services.payment.state_machine import (
    InvalidOrderStateTransitionError,
    OrderStateMachine,
    OrderStatus,
)

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
    - Resilient: handles order_code collision with automatic savepoint retries.
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
    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)

    for attempt in range(max_retries):
        numeric_code = secrets.randbelow(900_000_000) + 100_000_000
        order_candidate = Order(
            tenant_id=current_user.tenant_id,
            machine_id=machine.id,
            package_id=package.id,
            order_code=generate_order_code(),
            numeric_order_code=numeric_code,
            amount_vnd=package.price_vnd,
            status=OrderStatus.PENDING.value,
            payment_method=payload.payment_method,
            expires_at=expires_at,
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

    await db.commit()
    await db.refresh(new_order)
    return OrderResponse.model_validate(new_order)


@router.post(
    "/{id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order_payment(
    id: uuid.UUID,
    payload: PaymentCreateRequest = PaymentCreateRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    """
    Create a payment request (VietQR code & payment link) for an order.
    """
    payment = await PaymentService.create_order_payment(
        db=db,
        order_id=id,
        current_user=current_user,
        provider_name=payload.provider,
    )
    return PaymentResponse.model_validate(payment)


@router.get(
    "/{id}/payment-status",
    response_model=OrderPaymentStatusResponse,
)
async def get_order_payment_status(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderPaymentStatusResponse:
    """
    Query real-time payment status, QR code, and audit event ledger for an order.
    """
    return await PaymentService.get_order_payment_status(
        db=db,
        order_id=id,
        current_user=current_user,
    )


@router.get("", response_model=PaginatedOrderResponse)
async def list_orders(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (max 100)"),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by status (e.g. 'PENDING', 'PAID', 'COMPLETED', 'CANCELLED')",
    ),
    machine_id: uuid.UUID | None = Query(None, description="Filter by machine ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedOrderResponse:
    """
    Retrieve a paginated list of orders for the caller's tenant.
    - Scoped strictly to caller's tenant.
    - Supports optional filtering by order status and machine_id.
    - Deterministic ordering by created_at.desc(), id.desc().
    """
    base_filters = [Order.tenant_id == current_user.tenant_id]

    if status_filter:
        base_filters.append(Order.status.ilike(status_filter))
    if machine_id:
        base_filters.append(Order.machine_id == machine_id)

    # 1. Total count query
    count_query = select(func.count(Order.id)).where(*base_filters)
    total_count = (await db.execute(count_query)).scalar() or 0

    # 2. Paginated items query
    offset = (page - 1) * page_size
    items_query = (
        select(Order)
        .where(*base_filters)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_result = await db.execute(items_query)
    orders = items_result.scalars().all()

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    return PaginatedOrderResponse(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


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


@router.patch("/{id}", response_model=OrderResponse)
async def update_order_status(
    id: uuid.UUID,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "operator"])),
) -> OrderResponse:
    """
    Update an order's status (e.g. mark 'COMPLETED' after photo printing, or 'CANCELLED').
    - Restricted to 'admin' and 'operator' roles.
    - Validates state transition via OrderStateMachine.
    """
    result = await db.execute(
        select(Order)
        .where(
            Order.id == id,
            Order.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {id} not found",
        )

    target_status = OrderStateMachine.normalize_status(payload.status)
    try:
        OrderStateMachine.transition(order, target_status)
    except InvalidOrderStateTransitionError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    await db.commit()
    await db.refresh(order)

    return OrderResponse.model_validate(order)
