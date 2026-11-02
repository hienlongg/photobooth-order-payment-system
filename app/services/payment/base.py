from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentRequestData:
    order_code: str
    amount_vnd: int
    description: str
    numeric_order_code: int | None = None
    return_url: str | None = None
    cancel_url: str | None = None


@dataclass(frozen=True)
class PaymentResponseData:
    payment_id: str
    order_code: str
    amount_vnd: int
    checkout_url: str
    qr_code: str
    status: str
    account_number: str | None = None
    account_name: str | None = None
    bin: str | None = None


class PaymentProvider(ABC):
    """
    Abstract interface for payment gateway providers (e.g. PayOS, VNPay, MoMo).
    Decouples payment generation and webhook verification from concrete SDKs.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'fake_payos', 'payos')."""

    @abstractmethod
    async def create_payment_request(
        self, order_data: PaymentRequestData
    ) -> PaymentResponseData:
        """Request the payment gateway to generate a payment link and VietQR code."""

    @abstractmethod
    def generate_webhook_signature(self, data: dict[str, Any]) -> str:
        """Compute the HMAC signature for a webhook payload."""

    @abstractmethod
    def verify_webhook_signature(self, data: dict[str, Any], signature: str) -> bool:
        """Verify the authenticity of an incoming webhook signature using constant-time comparison."""

    @abstractmethod
    def create_signed_webhook_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Utility for tests and simulator to construct a fully signed webhook payload."""
