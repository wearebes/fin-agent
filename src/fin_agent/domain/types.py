from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fin_agent.domain.constants import EnvironmentName, RunStatus


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Research question to answer.")
    ticker: str | None = Field(default=None, description="Optional ticker symbol to bias retrieval.")
    template: str = Field(default="open_research", description="Prompt and output template name.")


class EvidenceItem(BaseModel):
    source: str
    summary: str


class TraceRecord(BaseModel):
    stage: str
    detail: str


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    environment: EnvironmentName
    request: ResearchRequest
    providers: dict[str, str]
    planned_stages: list[str]
    evidence: list[EvidenceItem]
    trace: list[TraceRecord]


class TraceResponse(BaseModel):
    run_id: str
    trace: list[TraceRecord]


JsonDict = dict[str, Any]
