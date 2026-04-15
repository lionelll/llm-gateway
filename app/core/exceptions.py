from app.models.provider import Provider


class GatewayError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class UpstreamProviderError(GatewayError):
    def __init__(
        self,
        status_code: int,
        detail: str,
        provider: Provider | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.provider = provider


class PricingNotConfiguredError(GatewayError):
    pass


class InsufficientBalanceError(GatewayError):
    pass
