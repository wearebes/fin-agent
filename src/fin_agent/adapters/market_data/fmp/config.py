from pydantic import BaseModel, Field, SecretStr


class FMPConfig(BaseModel):
    api_key: SecretStr | None = Field(default=None, description="FMP API key.")
    base_url: str = Field(
        default="https://financialmodelingprep.com/api/v3",
        description="FMP API base URL.",
    )
    enabled: bool = Field(default=True, description="Enable the FMP adapter.")
