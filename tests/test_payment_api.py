import asyncio
import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.payment import PaymentEvent
from app.services.payment.payos import FakePayOSProvider


async def create_test_order(
    client: AsyncClient, seed_data: dict, price_vnd: int = 70000
) -> dict:
    headers = {"Authorization": f"Bearer {seed_data['token']}"}
    payload = {
        "machine_id": str(seed_data["machine"].id),
        "package_id": str(seed_data["package"].id),
        "amount_vnd": price_vnd,
    }
    resp = await client.post("/api/v1/orders", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json()


# 1. SCENARIO: Valid payment -> PENDING to PAID
async def test_scenario_valid_payment(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    order_data = await create_test_order(client, seed_data)
    order_id = order_data["id"]
    headers = {"Authorization": f"Bearer {seed_data['token']}"}

    # Generate payment request
    p_resp = await client.post(f"/api/v1/orders/{order_id}/payments", headers=headers)
    assert p_resp.status_code == 201
    payment_info = p_resp.json()
    assert payment_info["checkout_url"] is not None
    assert payment_info["qr_code"] is not None
    assert payment_info["status"] == "PENDING"

    # Send valid signed webhook
    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order_data["numeric_order_code"],
        amount=order_data["amount_vnd"],
        reference="TX_VALID_001",
        description=order_data["order_code"],
    )
    wh_resp = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert wh_resp.status_code == 200
    assert wh_resp.json()["status"] == "PROCESSED"
    assert wh_resp.json()["order_status"] == "PAID"

    # Verify status endpoint
    status_resp = await client.get(
        f"/api/v1/orders/{order_id}/payment-status", headers=headers
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_paid"] is True
    assert status_resp.json()["order_status"] == "PAID"
    assert status_resp.json()["paid_at"] is not None
    assert status_resp.json()["events_count"] == 1


# 2. SCENARIO: Same webhook twice -> Only one payment transition
async def test_scenario_same_webhook_twice(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    order_data = await create_test_order(client, seed_data)
    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order_data["numeric_order_code"],
        amount=order_data["amount_vnd"],
        reference="TX_DUPLICATE_001",
    )

    # First delivery
    r1 = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "PROCESSED"
    assert r1.json()["is_duplicate"] is False

    # Replay delivery (Same webhook)
    r2 = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "DUPLICATE"
    assert r2.json()["is_duplicate"] is True

    # Check database: Exactly one payment event
    events = (
        (
            await db_session.execute(
                select(PaymentEvent).where(PaymentEvent.reference == "TX_DUPLICATE_001")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


# 3. SCENARIO: Invalid signature -> Reject webhook
async def test_scenario_invalid_signature(client: AsyncClient, seed_data: dict):
    order_data = await create_test_order(client, seed_data)
    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order_data["numeric_order_code"],
        amount=order_data["amount_vnd"],
        reference="TX_TAMPERED_001",
    )
    # Tamper with the signature
    webhook_payload["signature"] = "deadbeef" * 8

    resp = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid webhook signature"


# 4. SCENARIO: Wrong amount -> Flag for review
async def test_scenario_wrong_amount(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    order_data = await create_test_order(client, seed_data)
    provider = FakePayOSProvider()
    # Expected: 70,000 VND; Webhook sends: 50,000 VND (underpayment)
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order_data["numeric_order_code"],
        amount=50000,
        reference="TX_UNDERPAID_001",
    )

    resp = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "FLAGGED_FOR_REVIEW"
    assert resp.json()["order_status"] == "FLAGGED_FOR_REVIEW"

    # Check database
    order = (
        await db_session.execute(select(Order).where(Order.id == order_data["id"]))
    ).scalar_one()
    assert order.status == "FLAGGED_FOR_REVIEW"


# 5. SCENARIO: Expired order paid -> LATE_PAYMENT
async def test_scenario_expired_order_paid(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    order_data = await create_test_order(client, seed_data)
    order_id = order_data["id"]

    # Manually backdate expires_at in the database to simulate expiration
    order = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    order.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=5
    )
    await db_session.commit()

    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order.numeric_order_code,
        amount=order.amount_vnd,
        reference="TX_LATE_001",
    )

    resp = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "LATE_PAYMENT"
    assert resp.json()["order_status"] == "LATE_PAYMENT"

    # Check database
    await db_session.refresh(order)
    assert order.status == "LATE_PAYMENT"


# 6. SCENARIO: Unknown order code -> Record unmatched payment
async def test_scenario_unknown_order_code(
    client: AsyncClient, db_session: AsyncSession
):
    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=999999999,  # Non-existent order code
        amount=70000,
        reference="TX_UNMATCHED_001",
    )

    resp = await client.post("/api/v1/webhooks/fake", json=webhook_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "UNMATCHED"

    # Verify event stored in DB with order_id = None
    event = (
        await db_session.execute(
            select(PaymentEvent).where(PaymentEvent.reference == "TX_UNMATCHED_001")
        )
    ).scalar_one()
    assert event.order_id is None
    assert event.status == "UNMATCHED"


# 7. CHALLENGE: Send two identical webhooks concurrently using asyncio.gather()
async def test_concurrency_challenge_identical_webhooks(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """
    Challenge: Send two identical webhooks concurrently using asyncio.gather().
    Verify that only one payment event is accepted and the order is paid exactly once.
    """
    order_data = await create_test_order(client, seed_data)
    provider = FakePayOSProvider()
    webhook_payload = provider.create_signed_webhook_payload(
        order_code=order_data["numeric_order_code"],
        amount=order_data["amount_vnd"],
        reference="TX_CONCURRENT_RACE_001",
    )

    # Fire two identical webhook requests simultaneously
    resp1, resp2 = await asyncio.gather(
        client.post("/api/v1/webhooks/fake", json=webhook_payload),
        client.post("/api/v1/webhooks/fake", json=webhook_payload),
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    statuses = {resp1.json()["status"], resp2.json()["status"]}
    # One request must be PROCESSED; the other must be DUPLICATE
    assert "PROCESSED" in statuses
    assert "DUPLICATE" in statuses

    # Verify Database Invariant: Exactly one payment event and order paid once
    events = (
        (
            await db_session.execute(
                select(PaymentEvent).where(
                    PaymentEvent.reference == "TX_CONCURRENT_RACE_001"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].status == "PROCESSED"

    order = (
        await db_session.execute(select(Order).where(Order.id == order_data["id"]))
    ).scalar_one()
    assert order.status == "PAID"
    assert order.paid_at is not None
