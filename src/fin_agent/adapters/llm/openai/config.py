from pydantic import BaseModel, Field, SecretStr


class OpenAIConfig(BaseModel):
    model: str = Field(
        default="gpt-4.1-mini",
        description="OpenAI model used for research workflows.",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for the active LLM provider.",
    )
    base_url: str | None = Field(
        default=None,
        description="Optional custom OpenAI-compatible base URL.",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Provider-level timeout for OpenAI requests.",
    )
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for LLM calls.",
    )
