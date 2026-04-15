from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BalanceTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "balance_transactions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    usage_log_id: Mapped[str | None] = mapped_column(ForeignKey("usage_logs.id", ondelete="SET NULL"))
    request_id: Mapped[str | None] = mapped_column(String(64))
    transaction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    margin_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))

    user = relationship("User", back_populates="balance_transactions")
    api_key = relationship("APIKey", back_populates="balance_transactions")
    usage_log = relationship("UsageLog", back_populates="balance_transactions")
