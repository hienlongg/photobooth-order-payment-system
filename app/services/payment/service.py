import datetime
import secrets
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order
from app.models.payment import Payment, PaymentEvent
from app.models.user import User
from app.schemas.payment import (
    OrderPaymentStatusResponse,
    PaymentEventBrief,
    PaymentResponse,
    WebhookEventResponse,
)
from app.services.payment.base import PaymentProvider, PaymentRequestData
from app.services.payment.payos import FakePayOSProvider
from app.services.payment.state_machine import (
    InvalidOrderStateTransitionError,
    OrderStateMachine,
    OrderStatus,
)

# Statuses in which the order has already received (or is holding) customer money.
ALREADY_PAID_STATUSES = frozenset(
    {
        OrderStatus.PAID,
        OrderStatus.COMPLETED,
        OrderStatus.LATE_PAYMENT,
        OrderStatus.FLAGGED_FOR_REVIEW,
    }
)


class PaymentService:
    @staticmethod
    def get_provider(provider_name: str = "fake_payos") -> PaymentProvider:
        if provider_name == "fake_payos":
            return FakePayOSProvider()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported payment provider: '{provider_name}'",
        )

    @staticmethod
    async def _ensure_numeric_order_code(db: AsyncSession, order: Order) -> int:
        """Assigns and PERSISTS a unique numeric code for legacy orders lacking one,
        so webhooks quoting that code can be matched."""
        if order.numeric_order_code is not None:
            return order.numeric_order_code
        for _ in range(5):
            candidate = secrets.randbelow(900_000_000) + 100_000_000
            try:
                async with db.begin_nested():
                    order.numeric_order_code = candidate
                    await db.flush()
                return candidate
            except IntegrityError:
                order.numeric_order_code = None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to allocate a unique numeric order code. Please retry.",
        )

    @classmethod
    async def create_order_payment(
        cls,
        db: AsyncSession,
        order_id: UUID,
        current_user: User,
        provider_name: str = "fake_payos",
    ) -> Payment:
        """
        Creates a payment request and VietQR link for an existing order.
        """
        # 1. Fetch order belonging to user's tenant
        result = await db.execute(
            select(Order).where(
                Order.id == order_id,
                Order.tenant_id == current_user.tenant_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )

        # 2. Status verification
        current_status = OrderStateMachine.normalize_status(order.status)
        if current_status != OrderStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot generate payment for order in status '{order.status}'",
            )

        # 3. Check expiration
        now = datetime.datetime.now(datetime.UTC)
        if order.expires_at and now > order.expires_at:
            OrderStateMachine.transition(order, OrderStatus.EXPIRED)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has expired. Please create a new order.",
            )

        provider = cls.get_provider(provider_name)
        numeric_code = await cls._ensure_numeric_order_code(db, order)

        # 4. Request provider payment generation
        req_data = PaymentRequestData(
            order_code=order.order_code,
            numeric_order_code=numeric_code,
            amount_vnd=order.amount_vnd,
            description=f"PAY {order.order_code}",
        )
        resp_data = await provider.create_payment_request(req_data)

        # 5. Persist Payment record
        payment = Payment(
            tenant_id=order.tenant_id,
            order_id=order.id,
            provider=provider.provider_name,
            payment_reference=resp_data.payment_id,
            order_code=order.order_code,
            amount_vnd=order.amount_vnd,
            status=OrderStatus.PENDING.value,
            checkout_url=resp_data.checkout_url,
            qr_code=resp_data.qr_code,
            account_number=resp_data.account_number,
            account_name=resp_data.account_name,
            bin=resp_data.bin,
            expires_at=order.expires_at,
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        return payment

    @staticmethod
    def _parse_amount(raw: Any) -> int:
        """Strict VND amount parsing: whole, non-negative integers only."""
        value: int | None = None
        if isinstance(raw, bool) or raw is None:
            value = None
        elif isinstance(raw, int):
            value = raw
        elif isinstance(raw, float) and raw.is_integer():
            value = int(raw)
        elif isinstance(raw, str) and raw.strip().isdigit():
            value = int(raw.strip())
        if value is None or value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing 'amount' in webhook data",
            )
        return value

    @classmethod
    async def process_webhook(
        cls,
        db: AsyncSession,
        provider: PaymentProvider,
        raw_payload: dict[str, Any],
    ) -> WebhookEventResponse:
        """
        Processes inbound gateway webhooks with HMAC verification,
        dual-layer deduplication protection, and state machine transitions.
        """
        # 1. Cryptographic HMAC verification
        data = raw_payload.get("data")
        signature = raw_payload.get("signature")
        if not data or not signature or not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload format",
            )

        if not provider.verify_webhook_signature(data, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )

        # Extract transaction identifiers
        order_code_raw = data.get("orderCode")
        amount_received = cls._parse_amount(data.get("amount"))
        reference = str(data.get("reference") or data.get("paymentLinkId") or "")
        description = str(data.get("description", ""))
        # PayOS success code is "00"; anything else means the payment did not succeed.
        provider_code = str(data.get("code") or raw_payload.get("code") or "00")
        payment_failed = provider_code != "00"

        if not reference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing transaction reference in webhook data",
            )

        # 2. Check for duplicate event (Pre-check)
        existing_event = await db.execute(
            select(PaymentEvent).where(
                PaymentEvent.provider == provider.provider_name,
                PaymentEvent.reference == reference,
            )
        )
        if existing_event.scalar_one_or_none():
            return WebhookEventResponse(
                status="DUPLICATE",
                message="Duplicate webhook event ignored (already processed)",
                is_duplicate=True,
            )

        # 3. Locate matching order (by numeric_order_code, order_code, or description)
        order = None
        if order_code_raw is not None:
            # Check numeric match
            if isinstance(order_code_raw, int) or str(order_code_raw).isdigit():
                res = await db.execute(
                    select(Order).where(Order.numeric_order_code == int(order_code_raw))
                )
                order = res.scalar_one_or_none()

            # Check alphanumeric code match
            if not order:
                res = await db.execute(
                    select(Order).where(Order.order_code == str(order_code_raw))
                )
                order = res.scalar_one_or_none()

        # Check description substring match
        if not order and description:
            # The description (e.g. "PAY ABC123") must CONTAIN the order code. Use
            # strpos rather than LIKE so '%'/'_' are never treated as wildcards.
            res = await db.execute(
                select(Order)
                .where(
                    func.strpos(func.upper(description), func.upper(Order.order_code))
                    > 0
                )
                .limit(2)
            )
            candidates = res.scalars().all()
            # Ambiguous descriptions must not guess: fall through to UNMATCHED.
            order = candidates[0] if len(candidates) == 1 else None

        # SCENARIO: Unknown order code -> Record unmatched payment
        if not order:
            event = PaymentEvent(
                provider=provider.provider_name,
                reference=reference,
                order_code=str(order_code_raw) if order_code_raw else None,
                amount_vnd=amount_received,
                status="UNMATCHED",
                is_valid_signature=True,
                raw_payload=raw_payload,
                error_message=f"No matching order found for code '{order_code_raw}'",
            )
            try:
                async with db.begin_nested():
                    db.add(event)
                    await db.flush()
                await db.commit()
            except IntegrityError:
                # Concurrent duplicate for unmatched payment
                return WebhookEventResponse(
                    status="DUPLICATE",
                    message="Duplicate unmatched webhook ignored",
                    is_duplicate=True,
                )

            return WebhookEventResponse(
                status="UNMATCHED",
                message=f"Order '{order_code_raw}' not found. Payment recorded as unmatched.",
            )

        # SCENARIO: Gateway reports a failed/cancelled payment -> record only, never pay
        if payment_failed:
            event = PaymentEvent(
                tenant_id=order.tenant_id,
                order_id=order.id,
                provider=provider.provider_name,
                reference=reference,
                order_code=order.order_code,
                amount_vnd=amount_received,
                status="FAILED",
                is_valid_signature=True,
                raw_payload=raw_payload,
                error_message=(
                    f"Provider reported failure: code={provider_code}, "
                    f"desc={data.get('desc') or raw_payload.get('desc')}"
                ),
            )
            try:
                async with db.begin_nested():
                    db.add(event)
                    await db.flush()
                await db.commit()
            except IntegrityError:
                return WebhookEventResponse(
                    status="DUPLICATE",
                    message="Duplicate webhook event caught by unique constraint",
                    order_id=order.id,
                    order_status=order.status,
                    is_duplicate=True,
                )
            return WebhookEventResponse(
                status="FAILED",
                message="Provider reported a failed payment; order unchanged.",
                order_id=order.id,
                order_status=order.status,
                is_duplicate=False,
            )

        # 4. Acquire Row-Level Lock on Order (SELECT ... FOR UPDATE).
        # populate_existing() refreshes the identity-mapped instance with the locked
        # row; without it a stale cached `status` would be returned after waiting.
        locked_order_res = await db.execute(
            select(Order)
            .where(Order.id == order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        order = locked_order_res.scalar_one()

        current_status = OrderStateMachine.normalize_status(order.status)
        now = datetime.datetime.now(datetime.UTC)
        target_status: OrderStatus | None = OrderStatus.PAID
        event_status = "PROCESSED"
        err_msg = None

        if current_status in ALREADY_PAID_STATUSES:
            # SCENARIO: Order already holds money (distinct reference) -> double payment.
            # Never transition again; record the event so it can be reviewed/refunded.
            target_status = None
            event_status = "DUPLICATE_PAYMENT"
            err_msg = (
                f"Additional payment received for order already in status "
                f"'{current_status.value}' (possible double charge)"
            )

        # SCENARIO: Wrong amount -> Flag for review
        elif amount_received != order.amount_vnd:
            target_status = OrderStatus.FLAGGED_FOR_REVIEW
            event_status = "FLAGGED_FOR_REVIEW"
            err_msg = f"Amount mismatch: expected {order.amount_vnd} VND, received {amount_received} VND"

        # SCENARIO: Expired order paid -> LATE_PAYMENT
        elif (
            order.expires_at and now > order.expires_at
        ) or current_status == OrderStatus.EXPIRED:
            target_status = OrderStatus.LATE_PAYMENT
            event_status = "LATE_PAYMENT"
            err_msg = "Payment received after order expiration timeout"

        # SCENARIO: Transition not allowed (CANCELLED order, EXPIRED + wrong amount, ...)
        # Keep the money trail for manual review instead of returning 500.
        if target_status is not None and not OrderStateMachine.can_transition(
            order.status, target_status
        ):
            err_msg = (
                f"Payment of {amount_received} VND received but order in status "
                f"'{current_status.value}' cannot move to '{target_status.value}'; "
                f"manual review required"
            )
            target_status = None
            event_status = "REJECTED"

        # 5. Insert PaymentEvent protected by nested transaction (Savepoint)
        event = PaymentEvent(
            tenant_id=order.tenant_id,
            order_id=order.id,
            provider=provider.provider_name,
            reference=reference,
            order_code=order.order_code,
            amount_vnd=amount_received,
            status=event_status,
            is_valid_signature=True,
            raw_payload=raw_payload,
            error_message=err_msg,
        )

        try:
            async with db.begin_nested():
                db.add(event)
                await db.flush()
        except IntegrityError:
            # PostgreSQL caught concurrent insert with identical (provider, reference)
            order_id, order_status = order.id, order.status
            await db.rollback()  # release the row lock (expires loaded instances)
            return WebhookEventResponse(
                status="DUPLICATE",
                message="Duplicate webhook event caught by unique constraint",
                order_id=order_id,
                order_status=order_status,
                is_duplicate=True,
            )

        # 6. Apply state transition via OrderStateMachine
        if target_status is not None:
            try:
                OrderStateMachine.transition(order, target_status)
            except InvalidOrderStateTransitionError as exc:
                # Defensive: the pre-check should prevent this, but never lose the event.
                event.status = "REJECTED"
                event.error_message = str(exc)
                event_status = "REJECTED"
                err_msg = str(exc)
                target_status = None

        if target_status == OrderStatus.PAID:
            order.paid_at = now

        # Update associated Payment record if present
        if target_status is not None:
            p_res = await db.execute(
                select(Payment)
                .where(Payment.order_id == order.id)
                .order_by(Payment.created_at.desc())
            )
            payment = p_res.scalars().first()
            if payment:
                payment.status = target_status.value

        await db.commit()

        return WebhookEventResponse(
            status=event_status,
            message=err_msg or "Webhook processed successfully",
            order_id=order.id,
            order_status=order.status,
            is_duplicate=False,
        )

    @classmethod
    async def get_order_payment_status(
        cls,
        db: AsyncSession,
        order_id: UUID,
        current_user: User,
    ) -> OrderPaymentStatusResponse:
        """
        Queries real-time payment status, latest payment record, and webhook audit log.
        """
        res = await db.execute(
            select(Order)
            .options(selectinload(Order.payments), selectinload(Order.payment_events))
            .where(
                Order.id == order_id,
                Order.tenant_id == current_user.tenant_id,
            )
        )
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )

        is_paid = OrderStateMachine.normalize_status(order.status) == OrderStatus.PAID

        # Find latest payment record
        latest_payment = None
        if order.payments:
            sorted_payments = sorted(
                order.payments, key=lambda p: p.created_at, reverse=True
            )
            latest_payment = PaymentResponse.model_validate(sorted_payments[0])

        events_brief = [
            PaymentEventBrief.model_validate(ev)
            for ev in sorted(
                order.payment_events, key=lambda e: e.created_at, reverse=True
            )
        ]

        return OrderPaymentStatusResponse(
            order_id=order.id,
            order_code=order.order_code,
            order_status=order.status,
            amount_vnd=order.amount_vnd,
            is_paid=is_paid,
            payment_method=order.payment_method,
            paid_at=order.paid_at,
            expires_at=order.expires_at,
            latest_payment=latest_payment,
            events_count=len(events_brief),
            events=events_brief,
        )
