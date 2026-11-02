import uuid
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_vnd > 0", name="check_positive_order_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # "pending", "completed", "cancelled"
    payment_method: Mapped[str] = mapped_column(String(50), default="qr_pay", nullable=False)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
    machine: Mapped["Machine"] = relationship("Machine", back_populates="orders")
    package: Mapped["Package"] = relationship("Package", back_populates="orders")
