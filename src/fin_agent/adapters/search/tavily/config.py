from pydantic import BaseModel, Field, SecretStr


class TavilySearchConfig(BaseModel):
    max_results: int = Field(
        default=8,
        ge=1,
        description="Maximum number of search results returned by Tavily.",
    )
    api_key: SecretStr | None = Field(default=None, description="Tavily API key.")
    include_raw_content: bool = Field(
        default=False,
        description="Include raw content in search responses.",
    )
    search_depth: str = Field(
        default="advanced",
        description="Search depth: 'basic' for fast results, 'advanced' for deeper analysis.",
    )
    enabled: bool = Field(default=True, description="Enable the Tavily search adapter.")
