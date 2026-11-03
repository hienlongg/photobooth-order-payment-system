import hashlib
import hmac
import uuid
from typing import Any

from app.core.config import settings
from app.services.payment.base import (
    PaymentProvider,
    PaymentRequestData,
    PaymentResponseData,
)


class FakePayOSProvider(PaymentProvider):
    """
    Simulated PayOS / VietQR payment provider for local development, CI, and testing.
    Replicates PayOS's HMAC-SHA256 signature protocol and payload structures.
    """

    def __init__(
        self,
        checksum_key: str | None = None,
        client_id: str | None = None,
        api_key: str | None = None,
    ):
        self._checksum_key = checksum_key or settings.PAYOS_CHECKSUM_KEY
        self._client_id = client_id or settings.PAYOS_CLIENT_ID
        self._api_key = api_key or settings.PAYOS_API_KEY

    @property
    def provider_name(self) -> str:
        return "fake_payos"

    async def create_payment_request(
        self, order_data: PaymentRequestData
    ) -> PaymentResponseData:
        """
        Generates simulated checkout credentials:
        - VietQR payload standard string format (Napas compliant)
        - Simulated PayOS hosted payment link
        """
        payment_id = f"plink_{uuid.uuid4().hex[:16]}"
        fake_bin = "970422"  # MB Bank BIN
        fake_account_number = "088899998888"
        fake_account_name = "PHOTOBOOTH WONDERLAND"

        # Standard Napas 24/7 VietQR payload simulation
        qr_code = (
            f"00020101021238540010A00000072701240006{fake_bin}0114{fake_account_number}"
            f"520459995303704540{len(str(order_data.amount_vnd)):02d}{order_data.amount_vnd}"
            f"5802VN62{len(order_data.description):02d}08{len(order_data.description):02d}{order_data.description}"
            f"6304ABCD"
        )
        checkout_url = f"https://checkout.payos.vn/fake/{order_data.order_code}"

        return PaymentResponseData(
            payment_id=payment_id,
            order_code=order_data.order_code,
            amount_vnd=order_data.amount_vnd,
            checkout_url=checkout_url,
            qr_code=qr_code,
            status="PENDING",
            account_number=fake_account_number,
            account_name=fake_account_name,
            bin=fake_bin,
        )

    def canonicalize_data(self, data: dict[str, Any]) -> str:
        """
        PayOS Canonicalization:
        Sort keys alphabetically, join key=value with '&' for non-null values.
        """
        sorted_items = []
        for key in sorted(data.keys()):
            val = data[key]
            if val is not None:
                if isinstance(val, bool):
                    val_str = "true" if val else "false"
                else:
                    val_str = str(val)
                sorted_items.append(f"{key}={val_str}")
        return "&".join(sorted_items)

    def generate_webhook_signature(self, data: dict[str, Any]) -> str:
        """Computes HMAC-SHA256 hex digest over canonicalized data."""
        canonical_str = self.canonicalize_data(data)
        return hmac.new(
            self._checksum_key.encode("utf-8"),
            canonical_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_webhook_signature(self, data: dict[str, Any], signature: str) -> bool:
        """
        Validates webhook authenticity using constant-time comparison
        to mitigate timing attacks.
        """
        if not signature or not isinstance(signature, str):
            return False
        expected_sig = self.generate_webhook_signature(data)
        return hmac.compare_digest(expected_sig.lower(), signature.lower())

    def create_signed_webhook_payload(
        self,
        data: dict[str, Any] | None = None,
        *,
        order_code: int | str | None = None,
        amount: int | None = None,
        reference: str | None = None,
        description: str = "",
        code: str = "00",
        desc: str = "success",
    ) -> dict[str, Any]:
        """
        Constructs a fully signed PayOS webhook payload.
        Accepts either a pre-built data dict or individual kwargs.
        """
        if data is None:
            data = {
                "orderCode": order_code,
                "amount": amount,
                "description": description or f"Payment for {order_code}",
                "accountNumber": "088899998888",
                "reference": reference or f"REF-{uuid.uuid4().hex[:12]}",
                "transactionDateTime": "2026-03-30 14:00:00",
                "currency": "VND",
                "paymentLinkId": f"plink_{reference or 'default'}",
                "code": code,
                "desc": desc,
            }

        signature = self.generate_webhook_signature(data)
        return {
            "code": code,
            "desc": desc,
            "data": data,
            "signature": signature,
        }
