from pydantic import BaseModel, Field


class ResearchWorkflowConfig(BaseModel):
    max_tool_calls: int = Field(
        default=3,
        ge=1,
        description="Maximum number of tool calls allowed in one research run.",
    )
    max_iterations: int = Field(
        default=4,
        ge=1,
        description="Maximum workflow iterations before the run is terminated.",
    )
    evidence_limit: int = Field(
        default=12,
        ge=1,
        description="Maximum number of evidence records surfaced in the final report.",
    )
    enable_review: bool = Field(
        default=True,
        description="Run the review stage before persisting a report.",
    )
