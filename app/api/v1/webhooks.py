from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.payment import WebhookEventResponse
from app.services.payment.service import PaymentService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/fake",
    response_model=WebhookEventResponse,
    status_code=status.HTTP_200_OK,
)
async def handle_fake_payos_webhook(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> WebhookEventResponse:
    """
    Inbound webhook receiver for FakePayOS / VietQR notifications.
    - Verifies HMAC-SHA256 signature using constant-time digest comparison.
    - Guaranteed idempotent: duplicate webhooks do not trigger multiple order transitions.
    - Handles valid payments, amount discrepancies, late payments, and unmatched orders.
    """
    provider = PaymentService.get_provider("fake_payos")
    return await PaymentService.process_webhook(
        db=db,
        provider=provider,
        raw_payload=payload,
    )
