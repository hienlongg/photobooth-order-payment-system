import uuid
from typing import List
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    machines: Mapped[List["Machine"]] = relationship("Machine", back_populates="tenant", cascade="all, delete-orphan")
    packages: Mapped[List["Package"]] = relationship("Package", back_populates="tenant", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="tenant", cascade="all, delete-orphan")
