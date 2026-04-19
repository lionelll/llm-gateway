from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM Gateway"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://llm_gateway:llm_gateway@localhost:5432/llm_gateway"
    database_sync_url: str = "postgresql+psycopg://llm_gateway:llm_gateway@localhost:5432/llm_gateway"
    redis_url: str = "redis://localhost:6379/0"

    gateway_api_key_hash_secret: str = "change-me-in-production"
    provider_key_encryption_secret: str = "change-me-encryption-secret"
    api_key_rate_limit_per_minute: int = 60
    ip_rate_limit_per_minute: int = 120
    auto_disable_api_keys_on_zero_balance: bool = True
    default_max_tokens: int = 4096

    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    default_provider_timeout_seconds: int = 30

    # JWT
    jwt_secret: str = "change-me-jwt-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_success_url: str = "http://localhost:8000/portal?payment=success"
    stripe_cancel_url: str = "http://localhost:8000/portal?payment=cancel"

    enable_mock_provider: bool = True
    default_mock_model: str = "gpt-4o-mini"
    seed_admin_api_key: str = "gw_admin_local_key"
    seed_gateway_api_key: str = "gw_demo_local_key"
    seed_demo_payment_amount: Decimal = Decimal("200.00")
    seed_demo_margin_amount: Decimal = Decimal("40.00")

    seed_provider_name: str = ""
    seed_provider_type: str = "openai"
    seed_provider_base_url: str = ""
    seed_provider_api_key: str = ""
    seed_provider_supported_models: str = ""
    seed_provider_priority: int = 50
    seed_provider_weight: int = 10
    seed_provider_timeout_seconds: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def seed_provider_models(self) -> list[str]:
        if not self.seed_provider_supported_models.strip():
            return []
        return [item.strip() for item in self.seed_provider_supported_models.split(",") if item.strip()]

    @property
    def seed_demo_credited_amount(self) -> Decimal:
        return (self.seed_demo_payment_amount - self.seed_demo_margin_amount).quantize(Decimal("0.01"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
