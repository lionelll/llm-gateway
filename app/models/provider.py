from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(512))
    supported_models: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    health = relationship(
        "ProviderHealth",
        back_populates="provider",
        uselist=False,
        cascade="all, delete-orphan",
    )
    model_pricings = relationship("ModelPricing", back_populates="provider", cascade="all, delete-orphan")
    request_logs = relationship("RequestLog", back_populates="provider")
    usage_logs = relationship("UsageLog", back_populates="provider")
