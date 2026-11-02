import asyncio
import pytest
from app.services.payment.base import PaymentRequestData
from app.services.payment.payos import FakePayOSProvider


@pytest.fixture
def provider():
    return FakePayOSProvider(checksum_key="test_checksum_key_secret_123")


def test_payment_request_generation(provider: FakePayOSProvider):
    req_data = PaymentRequestData(
        order_code="ORD-ABC12345",
        amount_vnd=70000,
        description="PAY ORD-ABC12345",
        numeric_order_code=123456789,
    )

    resp = asyncio.run(provider.create_payment_request(req_data))

    assert resp.order_code == "ORD-ABC12345"
    assert resp.amount_vnd == 70000
    assert resp.status == "PENDING"
    assert resp.checkout_url == "https://checkout.payos.vn/fake/ORD-ABC12345"
    assert resp.payment_id.startswith("plink_")
    assert resp.qr_code.startswith("00020101")  # Standard VietQR header
    assert resp.bin == "970422"
    assert resp.account_number == "088899998888"


def test_canonicalize_data(provider: FakePayOSProvider):
    # Keys should be sorted alphabetically, non-null values joined by '&'
    raw_data = {
        "orderCode": 123456,
        "amount": 50000,
        "description": "Test order",
        "reference": "REF999",
        "nullableField": None,
    }
    canonical = provider.canonicalize_data(raw_data)
    expected = "amount=50000&description=Test order&orderCode=123456&reference=REF999"
    assert canonical == expected


def test_hmac_signature_verification_success(provider: FakePayOSProvider):
    payload = provider.create_signed_webhook_payload(
        order_code=123456,
        amount=70000,
        reference="TX_TEST_001",
        description="ORD-TEST",
    )

    assert "signature" in payload
    assert "data" in payload
    # Must be valid
    is_valid = provider.verify_webhook_signature(payload["data"], payload["signature"])
    assert is_valid is True


def test_hmac_signature_tampered_payload_rejected(provider: FakePayOSProvider):
    payload = provider.create_signed_webhook_payload(
        order_code=123456,
        amount=70000,
        reference="TX_TEST_001",
    )

    # Attacker tampers with the amount after signing
    payload["data"]["amount"] = 10000

    is_valid = provider.verify_webhook_signature(payload["data"], payload["signature"])
    assert is_valid is False


def test_hmac_signature_invalid_signature_string(provider: FakePayOSProvider):
    payload = provider.create_signed_webhook_payload(
        order_code=123456,
        amount=70000,
        reference="TX_TEST_001",
    )

    assert provider.verify_webhook_signature(payload["data"], "wrong_hex_signature") is False
    assert provider.verify_webhook_signature(payload["data"], "") is False
    assert provider.verify_webhook_signature(payload["data"], None) is False
