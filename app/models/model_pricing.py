from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ModelPricing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_pricings"
    __table_args__ = (UniqueConstraint("provider_id", "model_name", name="uq_model_pricings_provider_model"),)

    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0.000000"),
        nullable=False,
    )
    output_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0.000000"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider = relationship("Provider", back_populates="model_pricings")
