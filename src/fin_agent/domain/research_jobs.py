"""Durable research task records; credentials never belong in these models."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from fin_agent.domain.types import ResearchRequest, RunResult

JobStatus = Literal["queued", "running", "completed", "failed", "interrupted"]
ModelSource = Literal["default", "personal", "codex"]


def now() -> str:
    return datetime.now(UTC).isoformat()


class JobInput(BaseModel):
    request: ResearchRequest
    source: ModelSource = "default"
    client_id: str = Field(min_length=8, max_length=80, pattern=r"^[\w-]+$")


class ResearchJob(BaseModel):
    id: str
    owner: str = Field(exclude=True)
    client_id: str
    request: ResearchRequest
    source: ModelSource
    status: JobStatus = "queued"
    stage: str = "queued"
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    error: str | None = None
    result: RunResult | None = None

