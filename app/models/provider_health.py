from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProviderHealth(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_health"

    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), unique=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    circuit_opened_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(64), default="healthy", nullable=False)
    last_error_message: Mapped[str | None] = mapped_column(String(512))

    provider = relationship("Provider", back_populates="health")
