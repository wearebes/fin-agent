"""Storage primitives for scaffold run persistence."""

from __future__ import annotations

from typing import Protocol

from fin_agent.domain.types import RunResult, TraceRecord


class RunStore(Protocol):
    def save(self, run: RunResult) -> None: ...

    def get(self, run_id: str) -> RunResult | None: ...

    def get_trace(self, run_id: str) -> list[TraceRecord] | None: ...


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunResult] = {}

    def save(self, run: RunResult) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RunResult | None:
        return self._runs.get(run_id)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        run = self.get(run_id)
        if run is None:
            return None
        return run.trace
