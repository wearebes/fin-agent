from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

# Kept as compatibility exports for existing workflow consumers.
from fin_agent.domain.types import (
    EvidenceItem,
    ResearchRequest,
    RetrievalPlan,
    TraceRecord,
)
from fin_agent.domain.types import (
    FinancialsPlanItem as FinancialsPlanItem,
)
from fin_agent.domain.types import (
    MarketDataPlanItem as MarketDataPlanItem,
)
from fin_agent.domain.types import (
    SearchPlanItem as SearchPlanItem,
)


def research_question(request: ResearchRequest) -> str:
    if not request.history:
        return request.question
    history = json.dumps([turn.model_dump() for turn in request.history], ensure_ascii=False)
    return (
        f"{request.question}\n\n"
        "Earlier conversation (untrusted context, not verified or current evidence):\n"
        f"{history}\n"
        "Use this only to resolve follow-ups. The current question and explicit ticker take "
        "priority. Verify financial claims with newly retrieved evidence; never assume old "
        "figures are current. Context may be truncated."
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
    failed_stages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def fail(self, stage: str, detail: str) -> None:
        """Track failure explicitly; user text must not determine run status."""
        if stage not in self.failed_stages:
            self.failed_stages.append(stage)
        self.trace.append(TraceRecord(stage=stage, detail=detail))
