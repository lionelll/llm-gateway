import logging

from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

logger = logging.getLogger(__name__)


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    _api_key_encrypted: Mapped[str | None] = mapped_column("api_key", String(512))
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

    @property
    def api_key(self) -> str | None:
        """Decrypt the stored provider API key on read."""
        if not self._api_key_encrypted:
            return None
        try:
            from app.core.encryption import decrypt_value
            return decrypt_value(self._api_key_encrypted)
        except Exception:
            # Fallback for legacy plaintext values not yet encrypted
            logger.debug("Provider %s api_key not encrypted, returning as-is", self.name)
            return self._api_key_encrypted

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        """Encrypt the provider API key on write."""
        if value is None:
            self._api_key_encrypted = None
            return
        from app.core.encryption import encrypt_value
        self._api_key_encrypted = encrypt_value(value)
