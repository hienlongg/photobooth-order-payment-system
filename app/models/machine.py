import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.tenant import Tenant


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"
    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'offline', 'busy', 'maintenance')",
            name="check_machine_status",
        ),
        UniqueConstraint("tenant_id", "machine_code", name="uq_tenant_machine_code"),
        Index("ix_machines_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_machines_tenant_status", "tenant_id", "status"),
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
    machine_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="online", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="machines")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="machine")
