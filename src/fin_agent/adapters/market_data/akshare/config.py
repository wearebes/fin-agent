from pydantic import BaseModel, Field


class AKShareConfig(BaseModel):
    adjust: str = Field(
        default="qfq",
        description="Price adjustment method: qfq=前复权, hfq=后复权, ''=不复权.",
    )
    history_period: str = Field(
        default="1y",
        description="Historical data window used by the AKShare market data adapter.",
    )
    request_timeout_seconds: int = Field(
        default=15,
        ge=1,
        description="Provider-level timeout for AKShare data lookups.",
    )
    enabled: bool = Field(
        default=True, description="Enable the AKShare market data adapter."
    )
