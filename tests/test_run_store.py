from __future__ import annotations

import pytest

from fin_agent.domain.constants import (
    AssetType,
    DataFrequency,
    EnvironmentName,
    FinancialStatementType,
    RunStatus,
)
from fin_agent.domain.types import (
    EvidenceItem,
    FinancialsPlanItem,
    MarketDataPlanItem,
    ResearchRequest,
    RetrievalPlan,
    RunResult,
    SearchPlanItem,
    TraceRecord,
)
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.context import ResearchContext


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


def _make_full_context(run_id: str = "test-run-001") -> ResearchContext:
    return ResearchContext(
        run_id=run_id,
        request=ResearchRequest(question="Analyze AAPL", ticker="AAPL"),
        skill_instructions="Follow the valuation playbook.",
        plan=RetrievalPlan(
            search_queries=[
                SearchPlanItem(query="AAPL analysis", max_results=3),
                SearchPlanItem(query="AAPL earnings call", max_results=5),
            ],
            market_data=[
                MarketDataPlanItem(
                    ticker="AAPL",
                    asset_type=AssetType.STOCK,
                    frequency=DataFrequency.DAILY,
                    period="1y",
                ),
                MarketDataPlanItem(
                    ticker="BTC-USD",
                    asset_type=AssetType.CRYPTO,
                    frequency=DataFrequency.WEEKLY,
                    period="6mo",
                ),
            ],
            financials=[
                FinancialsPlanItem(
                    ticker="AAPL",
                    statement_type=FinancialStatementType.INCOME_STATEMENT,
                    frequency=DataFrequency.YEARLY,
                ),
                FinancialsPlanItem(
                    ticker="AAPL",
                    statement_type=FinancialStatementType.CASH_FLOW,
                    frequency=DataFrequency.QUARTERLY,
                ),
            ],
            fetch_company_info_tickers=["AAPL", "MSFT"],
            fetch_analyst_data_tickers=["AAPL"],
            fetch_crypto_tickers=["BTC-USD"],
        ),
        evidence=[EvidenceItem(source="search:AAPL analysis", summary="Some evidence")],
        trace=[TraceRecord(stage="intake", detail="Accepted research request")],
        report="",
        review_passed=None,
        review_feedback="",
        iteration=1,
        metadata={"custom_key": "custom_value"},
    )


class TestInMemoryRunStore:
    def test_save_context_then_get_context_in_memory(self):
        store = InMemoryRunStore()
        store.save_context("test-run-001", '{"run_id": "test-run-001"}')
        assert store.get_context("test-run-001") == '{"run_id": "test-run-001"}'

    def test_get_context_missing_returns_none_in_memory(self):
        store = InMemoryRunStore()
        assert store.get_context("nonexistent") is None

    def test_delete_context_clears_entry_in_memory(self):
        store = InMemoryRunStore()
        store.save_context("test-run-001", '{"run_id": "test-run-001"}')
        store.delete_context("test-run-001")
        assert store.get_context("test-run-001") is None

    def test_delete_context_missing_is_noop_in_memory(self):
        store = InMemoryRunStore()
        store.delete_context("nonexistent")  # must not raise


class TestSQLAlchemyRunStore:
    @pytest.fixture
    def store(self) -> SQLAlchemyRunStore:
        s = SQLAlchemyRunStore(database_url="sqlite:///:memory:")
        s.create_tables()
        return s

    def test_save_context_then_get_context_sql(self, store: SQLAlchemyRunStore):
        store.save(_make_run())
        store.save_context("test-run-001", '{"run_id": "test-run-001"}')
        assert store.get_context("test-run-001") == '{"run_id": "test-run-001"}'

    def test_get_context_missing_returns_none_sql(self, store: SQLAlchemyRunStore):
        assert store.get_context("nonexistent") is None

    def test_save_context_requires_existing_row(self, store: SQLAlchemyRunStore):
        store.save_context("never-saved", '{"run_id": "never-saved"}')
        assert store.get_context("never-saved") is None

    def test_delete_context_clears_entry_sql(self, store: SQLAlchemyRunStore):
        store.save(_make_run())
        store.save_context("test-run-001", '{"run_id": "test-run-001"}')
        store.delete_context("test-run-001")
        assert store.get_context("test-run-001") is None

    def test_delete_context_missing_is_noop_sql(self, store: SQLAlchemyRunStore):
        store.delete_context("nonexistent")  # must not raise

    def test_plan_round_trips_through_sql(self, store: SQLAlchemyRunStore):
        plan = RetrievalPlan(
            search_queries=[SearchPlanItem(query="AAPL analysis", max_results=3)],
            market_data=[],
            financials=[],
        )
        run = _make_run(status=RunStatus.AWAITING_APPROVAL, plan=plan)
        store.save(run)
        retrieved = store.get(run.run_id)
        assert retrieved is not None
        assert retrieved.plan is not None
        assert retrieved.plan.model_dump() == plan.model_dump()

    def test_plan_none_round_trips_through_sql(self, store: SQLAlchemyRunStore):
        run = _make_run(plan=None)
        store.save(run)
        retrieved = store.get(run.run_id)
        assert retrieved is not None
        assert retrieved.plan is None


class TestContextRoundTrip:
    def test_context_round_trips_full_research_context_in_memory(self):
        store = InMemoryRunStore()
        ctx = _make_full_context()
        store.save(_make_run(run_id=ctx.run_id, status=RunStatus.AWAITING_APPROVAL, plan=ctx.plan))
        store.save_context(ctx.run_id, ctx.model_dump_json())

        ctx_json = store.get_context(ctx.run_id)
        assert ctx_json is not None
        restored = ResearchContext.model_validate_json(ctx_json)
        assert restored.model_dump() == ctx.model_dump()

    def test_context_round_trips_full_research_context_sql(self):
        store = SQLAlchemyRunStore(database_url="sqlite:///:memory:")
        store.create_tables()
        ctx = _make_full_context()
        store.save(_make_run(run_id=ctx.run_id, status=RunStatus.AWAITING_APPROVAL, plan=ctx.plan))
        store.save_context(ctx.run_id, ctx.model_dump_json())

        ctx_json = store.get_context(ctx.run_id)
        assert ctx_json is not None
        restored = ResearchContext.model_validate_json(ctx_json)
        assert restored.model_dump() == ctx.model_dump()
