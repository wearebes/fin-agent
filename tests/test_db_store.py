from __future__ import annotations

import json

import pytest

from fin_agent.domain.constants import EnvironmentName, RunStatus
from fin_agent.domain.types import (
    EvidenceItem,
    ResearchRequest,
    RunResult,
    TraceRecord,
)
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.run_store import InMemoryRunStore


def _make_run(run_id: str = "test-run-001", **overrides) -> RunResult:
    defaults = dict(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        environment=EnvironmentName.LOCAL,
        request=ResearchRequest(question="Test question", ticker="AAPL"),
        providers={"llm": "openai", "search": "exa"},
        planned_stages=["intake", "plan", "retrieve", "tool-exec", "synthesize", "persist"],
        report="# Test Report\n\nAAPL analysis summary.",
        evidence=[
            EvidenceItem(source="search:AAPL", summary="Search result for AAPL"),
            EvidenceItem(source="market_data:AAPL", summary="AAPL close=152.0"),
        ],
        trace=[
            TraceRecord(stage="intake", detail="Accepted research request"),
            TraceRecord(stage="plan", detail="Generated retrieval plan"),
            TraceRecord(stage="persist", detail="Run persisted"),
        ],
    )
    defaults.update(overrides)
    return RunResult(**defaults)


class TestInMemoryRunStore:
    def test_save_and_get(self):
        store = InMemoryRunStore()
        run = _make_run()
        store.save(run)
        result = store.get("test-run-001")
        assert result is not None
        assert result.run_id == "test-run-001"
        assert result.status == RunStatus.COMPLETED
        assert result.report == "# Test Report\n\nAAPL analysis summary."
        assert len(result.evidence) == 2
        assert len(result.trace) == 3

    def test_get_missing_returns_none(self):
        store = InMemoryRunStore()
        assert store.get("nonexistent") is None

    def test_get_trace(self):
        store = InMemoryRunStore()
        store.save(_make_run())
        trace = store.get_trace("test-run-001")
        assert trace is not None
        assert len(trace) == 3
        assert trace[0].stage == "intake"

    def test_get_trace_missing_returns_none(self):
        store = InMemoryRunStore()
        assert store.get_trace("nonexistent") is None

    def test_save_overwrites(self):
        store = InMemoryRunStore()
        store.save(_make_run(status=RunStatus.COMPLETED))
        store.save(_make_run(status=RunStatus.FAILED))
        result = store.get("test-run-001")
        assert result is not None
        assert result.status == RunStatus.FAILED


class TestSQLAlchemyRunStore:
    @pytest.fixture
    def store(self) -> SQLAlchemyRunStore:
        s = SQLAlchemyRunStore(database_url="sqlite:///:memory:")
        s.create_tables()
        return s

    def test_save_and_get(self, store: SQLAlchemyRunStore):
        run = _make_run()
        store.save(run)
        result = store.get("test-run-001")
        assert result is not None
        assert result.run_id == "test-run-001"
        assert result.status == RunStatus.COMPLETED
        assert result.environment == EnvironmentName.LOCAL
        assert result.request.question == "Test question"
        assert result.request.ticker == "AAPL"
        assert result.providers == {"llm": "openai", "search": "exa"}
        assert len(result.planned_stages) == 6
        assert "Test Report" in result.report
        assert len(result.evidence) == 2
        assert result.evidence[0].source == "search:AAPL"
        assert len(result.trace) == 3
        assert result.trace[0].stage == "intake"

    def test_get_missing_returns_none(self, store: SQLAlchemyRunStore):
        assert store.get("nonexistent") is None

    def test_get_trace(self, store: SQLAlchemyRunStore):
        store.save(_make_run())
        trace = store.get_trace("test-run-001")
        assert trace is not None
        assert len(trace) == 3
        assert trace[1].stage == "plan"

    def test_get_trace_missing_returns_none(self, store: SQLAlchemyRunStore):
        assert store.get_trace("nonexistent") is None

    def test_save_overwrites(self, store: SQLAlchemyRunStore):
        store.save(_make_run(status=RunStatus.COMPLETED))
        store.save(_make_run(status=RunStatus.FAILED))
        result = store.get("test-run-001")
        assert result is not None
        assert result.status == RunStatus.FAILED

    def test_multiple_runs(self, store: SQLAlchemyRunStore):
        store.save(_make_run("run-a"))
        store.save(_make_run("run-b", status=RunStatus.FAILED))
        assert store.get("run-a") is not None
        assert store.get("run-a").status == RunStatus.COMPLETED
        assert store.get("run-b") is not None
        assert store.get("run-b").status == RunStatus.FAILED

    def test_list_runs(self, store: SQLAlchemyRunStore):
        store.save(_make_run("run-a"))
        store.save(_make_run("run-b"))
        runs = store.list_runs()
        assert len(runs) == 2
        run_ids = {r.run_id for r in runs}
        assert run_ids == {"run-a", "run-b"}

    def test_list_runs_pagination(self, store: SQLAlchemyRunStore):
        for i in range(5):
            store.save(_make_run(f"run-{i}"))
        page1 = store.list_runs(limit=2, offset=0)
        assert len(page1) == 2
        page2 = store.list_runs(limit=2, offset=2)
        assert len(page2) == 2
        page3 = store.list_runs(limit=2, offset=4)
        assert len(page3) == 1

    def test_round_trip_preserves_all_fields(self, store: SQLAlchemyRunStore):
        run = _make_run()
        store.save(run)
        result = store.get("test-run-001")
        assert result is not None
        assert result.model_dump() == run.model_dump()

    def test_empty_evidence_and_trace(self, store: SQLAlchemyRunStore):
        run = _make_run(evidence=[], trace=[], report="")
        store.save(run)
        result = store.get("test-run-001")
        assert result is not None
        assert result.evidence == []
        assert result.trace == []
        assert result.report == ""

    def test_request_without_ticker(self, store: SQLAlchemyRunStore):
        run = _make_run(request=ResearchRequest(question="General question"))
        store.save(run)
        result = store.get("test-run-001")
        assert result is not None
        assert result.request.ticker is None
        assert result.request.question == "General question"


class TestContainerStoreSelection:
    def test_default_uses_memory(self, monkeypatch):
        monkeypatch.setenv("FIN_AGENT__OPENAI__API_KEY", "sk-test")
        monkeypatch.setenv("FIN_AGENT__SEARCH__API_KEY", "search-test")
        from fin_agent.bootstrap.container import build_container
        from fin_agent.bootstrap.settings import load_settings

        settings = load_settings("test")
        container = build_container(settings)
        assert isinstance(container.run_store, InMemoryRunStore)

    def test_sql_backend(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FIN_AGENT__OPENAI__API_KEY", "sk-test")
        monkeypatch.setenv("FIN_AGENT__SEARCH__API_KEY", "search-test")
        monkeypatch.setenv("FIN_AGENT__DATABASE__BACKEND", "sql")
        db_path = tmp_path / "test.db"
        monkeypatch.setenv(
            "FIN_AGENT__DATABASE__URL",
            f"sqlite:///{db_path}",
        )
        from fin_agent.bootstrap.container import build_container
        from fin_agent.bootstrap.settings import load_settings

        settings = load_settings("test")
        container = build_container(settings)
        assert isinstance(container.run_store, SQLAlchemyRunStore)
