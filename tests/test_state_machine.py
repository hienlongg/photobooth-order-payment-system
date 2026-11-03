import pytest

from app.models.order import Order
from app.services.payment.state_machine import (
    InvalidOrderStateTransitionError,
    OrderStateMachine,
    OrderStatus,
)


def test_valid_transitions():
    order = Order(status="PENDING")
    OrderStateMachine.transition(order, OrderStatus.PAID)
    assert order.status == "PAID"

    OrderStateMachine.transition(order, OrderStatus.COMPLETED)
    assert order.status == "COMPLETED"


def test_invalid_terminal_transition():
    order = Order(status="COMPLETED")
    with pytest.raises(InvalidOrderStateTransitionError):
        OrderStateMachine.transition(order, OrderStatus.PAID)


def test_idempotent_transition():
    order = Order(status="PAID")
    OrderStateMachine.transition(order, OrderStatus.PAID)
    assert order.status == "PAID"


def test_flagged_for_review_transition():
    order = Order(status="PENDING")
    OrderStateMachine.transition(order, OrderStatus.FLAGGED_FOR_REVIEW)
    assert order.status == "FLAGGED_FOR_REVIEW"

    # From FLAGGED_FOR_REVIEW can be approved to PAID
    OrderStateMachine.transition(order, OrderStatus.PAID)
    assert order.status == "PAID"


def test_late_payment_transition():
    order = Order(status="EXPIRED")
    OrderStateMachine.transition(order, OrderStatus.LATE_PAYMENT)
    assert order.status == "LATE_PAYMENT"


def test_case_insensitive_handling():
    order = Order(status="pending")
    assert OrderStateMachine.can_transition(order.status, OrderStatus.PAID) is True
    OrderStateMachine.transition(order, OrderStatus.PAID)
    assert order.status == "PAID"
