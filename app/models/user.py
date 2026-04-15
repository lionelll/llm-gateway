from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    # Self-registration fields (nullable for backward-compat with admin-created users)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    balance_transactions = relationship("BalanceTransaction", back_populates="user")
    request_logs = relationship("RequestLog", back_populates="user")
    usage_logs = relationship("UsageLog", back_populates="user")
