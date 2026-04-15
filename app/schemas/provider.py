from datetime import datetime

from pydantic import BaseModel


class ProviderRead(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    supported_models: list[str]
    priority: int
    weight: int
    is_active: bool
    timeout_seconds: int
    health_status: str
    consecutive_failures: int
    circuit_opened_until: datetime | None
