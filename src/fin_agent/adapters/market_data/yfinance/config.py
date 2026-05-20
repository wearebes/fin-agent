from pydantic import BaseModel, Field


class YFinanceConfig(BaseModel):
    history_period: str = Field(
        default="1y",
        description="Historical data window used by the default market data adapter.",
    )
    request_timeout_seconds: int = Field(
        default=15,
        ge=1,
        description="Provider-level timeout for market data lookups.",
    )
    enabled: bool = Field(default=True, description="Enable the market data adapter.")
