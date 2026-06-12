"""Storage primitives for scaffold run persistence."""

from __future__ import annotations

from typing import Protocol

from fin_agent.domain.types import RunResult, TraceRecord


class RunStore(Protocol):
    def save(self, run: RunResult) -> None: ...

    def get(self, run_id: str) -> RunResult | None: ...

    def get_trace(self, run_id: str) -> list[TraceRecord] | None: ...

    def save_context(self, run_id: str, context_json: str) -> None: ...

    def get_context(self, run_id: str) -> str | None: ...

    def delete_context(self, run_id: str) -> None: ...


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunResult] = {}
        self._contexts: dict[str, str] = {}

    def save(self, run: RunResult) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RunResult | None:
        return self._runs.get(run_id)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        run = self.get(run_id)
        if run is None:
            return None
        return run.trace

    def save_context(self, run_id: str, context_json: str) -> None:
        self._contexts[run_id] = context_json

    def get_context(self, run_id: str) -> str | None:
        return self._contexts.get(run_id)

    def delete_context(self, run_id: str) -> None:
        self._contexts.pop(run_id, None)
