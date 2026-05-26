"""SQLAlchemy-backed RunStore implementation."""

from __future__ import annotations

import json
import logging
from typing import Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fin_agent.domain.types import (
    EvidenceItem,
    ResearchRequest,
    RunResult,
    TraceRecord,
)
from fin_agent.storage.models import Base, RunRow, TraceRecordRow

logger = logging.getLogger(__name__)


def _row_to_result(row: RunRow) -> RunResult:
    return RunResult(
        run_id=row.run_id,
        status=row.status,
        environment=row.environment,
        request=ResearchRequest.model_validate_json(row.request_json),
        providers=json.loads(row.providers_json),
        planned_stages=json.loads(row.planned_stages_json),
        report=row.report,
        evidence=[EvidenceItem.model_validate(e) for e in json.loads(row.evidence_json)],
        trace=[TraceRecord(stage=t.stage, detail=t.detail) for t in row.trace_records],
    )


def _result_to_row(result: RunResult) -> RunRow:
    return RunRow(
        run_id=result.run_id,
        status=result.status.value if hasattr(result.status, "value") else str(result.status),
        environment=result.environment.value
        if hasattr(result.environment, "value")
        else str(result.environment),
        request_json=result.request.model_dump_json(),
        providers_json=json.dumps(result.providers),
        planned_stages_json=json.dumps(result.planned_stages),
        report=result.report,
        evidence_json=json.dumps(
            [e.model_dump(mode="json") for e in result.evidence]
        ),
        trace_records=[
            TraceRecordRow(stage=t.stage, detail=t.detail, seq=i)
            for i, t in enumerate(result.trace)
        ],
    )


class SQLAlchemyRunStore:
    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._engine = create_engine(database_url, echo=echo)

    def create_tables(self) -> None:
        Base.metadata.create_all(self._engine)

    def save(self, run: RunResult) -> None:
        with Session(self._engine) as session:
            existing = session.get(RunRow, run.run_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(_result_to_row(run))
            session.commit()

    def get(self, run_id: str) -> RunResult | None:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            return _row_to_result(row)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            return [TraceRecord(stage=t.stage, detail=t.detail) for t in row.trace_records]

    def list_runs(self, *, limit: int = 50, offset: int = 0) -> Sequence[RunResult]:
        with Session(self._engine) as session:
            rows = (
                session.query(RunRow)
                .order_by(RunRow.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [_row_to_result(r) for r in rows]

    @property
    def engine(self):
        return self._engine
