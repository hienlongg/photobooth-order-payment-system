from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.models.order import Order


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    LATE_PAYMENT = "LATE_PAYMENT"
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"


class InvalidOrderStateTransitionError(Exception):
    """Raised when an order transition violates the state machine rules."""

    def __init__(self, from_state: str, to_state: str, reason: str | None = None):
        msg = f"Cannot transition order from '{from_state}' to '{to_state}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason


class OrderStateMachine:
    """
    Enforces deterministic state transitions for Orders.
    Prevents duplicate fulfillment, re-opening closed orders, and race-condition corruption.
    """

    ALLOWED_TRANSITIONS: ClassVar[dict[OrderStatus, set[OrderStatus]]] = {
        OrderStatus.PENDING: {
            OrderStatus.PAID,
            OrderStatus.COMPLETED,  # operators may complete directly
            OrderStatus.FLAGGED_FOR_REVIEW,
            OrderStatus.EXPIRED,
            OrderStatus.LATE_PAYMENT,
            OrderStatus.CANCELLED,
        },
        OrderStatus.EXPIRED: {
            OrderStatus.LATE_PAYMENT,
            OrderStatus.CANCELLED,
        },
        OrderStatus.FLAGGED_FOR_REVIEW: {
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        },
        OrderStatus.PAID: {
            OrderStatus.COMPLETED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.LATE_PAYMENT: {
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        },
        OrderStatus.COMPLETED: set(),  # Terminal state
        OrderStatus.CANCELLED: set(),  # Terminal state
    }

    @classmethod
    def normalize_status(cls, status: str) -> OrderStatus:
        """Converts case-insensitive strings to OrderStatus enum."""
        try:
            return OrderStatus(status.upper())
        except ValueError:
            raise InvalidOrderStateTransitionError(
                from_state=status,
                to_state="UNKNOWN",
                reason=f"Status '{status}' is not a recognized OrderStatus",
            )

    @classmethod
    def can_transition(cls, from_status_str: str, to_status: OrderStatus) -> bool:
        current = cls.normalize_status(from_status_str)
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        return to_status in allowed

    @classmethod
    def transition(cls, order: "Order", to_status: OrderStatus) -> "Order":
        current = cls.normalize_status(order.status)
        if current == to_status:
            # Idempotent: already in target state
            return order

        if not cls.can_transition(order.status, to_status):
            raise InvalidOrderStateTransitionError(
                from_state=order.status,
                to_state=to_status.value,
                reason=f"Transition from '{current.value}' to '{to_status.value}' is forbidden",
            )

        order.status = to_status.value
        return order
