from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Kept as compatibility exports for existing workflow consumers.
from fin_agent.domain.types import (
    EvidenceItem,
    FinancialsPlanItem,
    MarketDataPlanItem,
    ResearchRequest,
    RetrievalPlan,
    SearchPlanItem,
    TraceRecord,
)

__all__ = [
    "EvidenceItem",
    "FinancialsPlanItem",
    "MarketDataPlanItem",
    "ResearchContext",
    "ResearchRequest",
    "RetrievalPlan",
    "SearchPlanItem",
    "ToolCallRecord",
    "TraceRecord",
]


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""


class ResearchContext(BaseModel):
    run_id: str = ""
    request: ResearchRequest
    skill_instructions: str = Field(
        default="",
        description=(
            "Resolved body of `request.selected_skill`, if any — prepended "
            "verbatim to stage system prompts. Empty means 'no skill selected "
            "or it resolved to a body-less structural skill', both of which "
            "are deliberate no-ops."
        ),
    )
    plan: RetrievalPlan = Field(default_factory=RetrievalPlan)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    trace: list[TraceRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    report: str = ""
    review_passed: bool | None = None
    review_feedback: str = ""
    iteration: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
