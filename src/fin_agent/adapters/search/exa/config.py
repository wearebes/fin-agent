from pydantic import BaseModel, Field, SecretStr


class ExaSearchConfig(BaseModel):
    max_results: int = Field(
        default=8,
        ge=1,
        description="Maximum number of search results returned by the default search adapter.",
    )
    api_key: SecretStr | None = Field(default=None, description="Search provider API key.")
    include_text: bool = Field(
        default=True,
        description="Include full text snippets in search responses.",
    )
    enabled: bool = Field(default=True, description="Enable the search adapter.")
