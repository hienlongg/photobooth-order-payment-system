import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.machine import Machine
    from app.models.package import Package
    from app.models.payment import Payment, PaymentEvent
    from app.models.tenant import Tenant


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_vnd > 0", name="check_positive_order_amount"),
        CheckConstraint(
            "status IN ('PENDING', 'PAID', 'COMPLETED', 'CANCELLED', 'EXPIRED', 'LATE_PAYMENT', 'FLAGGED_FOR_REVIEW', 'pending', 'paid', 'completed', 'cancelled')",
            name="check_valid_order_status",
        ),
        # High-speed composite indexes for tenant dashboards
        Index("ix_orders_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_orders_tenant_machine", "tenant_id", "machine_id"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("machines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    numeric_order_code: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(50), default="qr_pay", nullable=False
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
    machine: Mapped["Machine"] = relationship("Machine", back_populates="orders")
    package: Mapped["Package"] = relationship("Package", back_populates="orders")
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )
    payment_events: Mapped[list["PaymentEvent"]] = relationship(
        "PaymentEvent", back_populates="order"
    )
