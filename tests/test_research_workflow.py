from __future__ import annotations

import json
from typing import Any

import pytest

from fin_agent.adapters.market_data import MarketDataProvider
from fin_agent.adapters.search import SearchProvider
from fin_agent.domain.constants import (
    AssetType,
    DataFrequency,
    FinancialStatementType,
)
from fin_agent.domain.types import (
    AnalystRecommendation,
    AnalystResponse,
    CompanyInfo,
    CryptoDataPoint,
    CryptoDataResponse,
    EvidenceItem,
    FinancialStatementRecord,
    FinancialStatementResponse,
    LLMMessage,
    LLMResponse,
    MarketDataPoint,
    MarketDataResponse,
    ResearchRequest,
    SearchResponse,
    SearchResultItem,
    TraceRecord,
)
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext
from fin_agent.workflows.research.graph import build_stage_plan, execute_workflow
from fin_agent.workflows.research.stages import StageDeps, ToolRegistry
from fin_agent.workflows.research.stages.core import intake, plan, retrieve
from fin_agent.workflows.research.stages.pipeline import (
    persist,
    review,
    synthesize,
    tool_exec,
)


class StubLLM:
    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return LLMResponse(
            message=LLMMessage(role="assistant", content="```done```")
        )


PLAN_JSON = json.dumps({
    "search_queries": [{"query": "AAPL analysis", "max_results": 3}],
    "market_data": [
        {"ticker": "AAPL", "asset_type": "stock", "frequency": "daily", "period": "1y"}
    ],
    "financials": [
        {"ticker": "AAPL", "statement_type": "income_statement", "frequency": "yearly"}
    ],
    "fetch_company_info_tickers": ["AAPL"],
    "fetch_analyst_data_tickers": ["AAPL"],
    "fetch_crypto_tickers": [],
})

SYNTHESIZE_RESPONSE = LLMResponse(
    message=LLMMessage(
        role="assistant",
        content="# Research Report\n\nAAPL is a strong buy based on...",
    )
)

REVIEW_RESPONSE = LLMResponse(
    message=LLMMessage(
        role="assistant",
        content='{"passed": true, "feedback": "Report is adequate."}',
    )
)


class StubSearch:
    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            query=query,
            results=[
                SearchResultItem(
                    title=f"Result for {query}",
                    url="https://example.com",
                    text="Sample search result text",
                )
            ],
        )


class StubMarketData:
    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        from datetime import date

        return MarketDataResponse(
            ticker=ticker,
            asset_type=asset_type,
            data=[
                MarketDataPoint(
                    ticker=ticker,
                    asset_type=asset_type,
                    trade_date=date(2025, 1, 1),
                    open=150.0,
                    high=155.0,
                    low=149.0,
                    close=152.0,
                    volume=1000000,
                )
            ],
        )

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        return FinancialStatementResponse(
            ticker=ticker,
            statement_type=statement_type,
            data=[
                FinancialStatementRecord(
                    ticker=ticker,
                    statement_type=statement_type,
                    fiscal_year=2024,
                    total_revenue=394328000000.0,
                    net_income=99803000000.0,
                )
            ],
        )

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        return AnalystResponse(
            ticker=ticker,
            recommendations=[
                AnalystRecommendation(
                    ticker=ticker,
                    firm="Goldman Sachs",
                    rating="Buy",
                    target_price=200.0,
                )
            ],
        )

    def get_company_info(self, ticker: str) -> CompanyInfo:
        return CompanyInfo(
            ticker=ticker,
            name="Apple Inc.",
            sector="Technology",
            market_cap=3000000000000.0,
        )

    def get_crypto_data(
        self,
        ticker: str,
        *,
        period: str | None = None,
    ) -> CryptoDataResponse:
        from datetime import date

        return CryptoDataResponse(
            ticker=ticker,
            data=[
                CryptoDataPoint(
                    ticker=ticker,
                    trade_date=date(2025, 1, 1),
                    open=42000.0,
                    high=43500.0,
                    low=41500.0,
                    close=42800.0,
                    volume=50000000000.0,
                )
            ],
        )


@pytest.fixture
def config() -> ResearchWorkflowConfig:
    return ResearchWorkflowConfig(
        max_tool_calls=3,
        max_iterations=2,
        evidence_limit=20,
        enable_review=True,
    )


@pytest.fixture
def stub_search() -> StubSearch:
    return StubSearch()


@pytest.fixture
def stub_market_data() -> StubMarketData:
    return StubMarketData()


def _make_deps(
    config: ResearchWorkflowConfig,
    llm_responses: list[LLMResponse] | None = None,
    search: SearchProvider | None = None,
    market_data: MarketDataProvider | None = None,
) -> StageDeps:
    return StageDeps(
        llm=StubLLM(llm_responses),
        search=search or StubSearch(),
        market_data=market_data or StubMarketData(),
        config=config,
    )


class TestResearchContext:
    def test_default_context(self):
        ctx = ResearchContext(request=ResearchRequest(question="test"))
        assert ctx.run_id == ""
        assert ctx.evidence == []
        assert ctx.trace == []
        assert ctx.report == ""
        assert ctx.metadata == {}

    def test_metadata_extensibility(self):
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            metadata={"custom_key": "custom_value"},
        )
        assert ctx.metadata["custom_key"] == "custom_value"


class TestBuildStagePlan:
    def test_with_review(self, config: ResearchWorkflowConfig):
        stages = build_stage_plan(config)
        expected = [
            "intake", "plan", "retrieve", "tool-exec",
            "synthesize", "review", "persist",
        ]
        assert stages == expected

    def test_without_review(self):
        cfg = ResearchWorkflowConfig(enable_review=False)
        stages = build_stage_plan(cfg)
        expected = ["intake", "plan", "retrieve", "tool-exec", "synthesize", "persist"]
        assert stages == expected


class TestIntakeStage:
    @pytest.mark.asyncio
    async def test_intake_assigns_run_id(self, config: ResearchWorkflowConfig):
        ctx = ResearchContext(request=ResearchRequest(question="What about AAPL?"))
        deps = _make_deps(config)
        result = await intake(ctx, deps)
        assert len(result.run_id) == 32
        assert len(result.trace) == 1
        assert result.trace[0].stage == "intake"

    @pytest.mark.asyncio
    async def test_intake_with_ticker(self, config: ResearchWorkflowConfig):
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        deps = _make_deps(config)
        result = await intake(ctx, deps)
        assert "AAPL" in result.trace[0].detail


class TestPlanStage:
    @pytest.mark.asyncio
    async def test_plan_parses_llm_json(self, config: ResearchWorkflowConfig):
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        ctx = ResearchContext(request=ResearchRequest(question="Analyze AAPL", ticker="AAPL"))
        deps = _make_deps(config, llm_responses=[plan_response])
        result = await plan(ctx, deps)
        assert len(result.plan.search_queries) == 1
        assert result.plan.search_queries[0].query == "AAPL analysis"
        assert len(result.plan.market_data) == 1
        assert len(result.plan.financials) == 1
        assert "AAPL" in result.plan.fetch_company_info_tickers

    @pytest.mark.asyncio
    async def test_plan_fallback_on_bad_llm(self, config: ResearchWorkflowConfig):
        bad_response = LLMResponse(
            message=LLMMessage(role="assistant", content="not json at all")
        )
        ctx = ResearchContext(request=ResearchRequest(question="Analyze AAPL", ticker="AAPL"))
        deps = _make_deps(config, llm_responses=[bad_response])
        result = await plan(ctx, deps)
        assert len(result.plan.search_queries) >= 1
        assert "AAPL" in result.plan.market_data[0].ticker


class TestRetrieveStage:
    @pytest.mark.asyncio
    async def test_retrieve_collects_evidence(self, config: ResearchWorkflowConfig):
        from fin_agent.workflows.research.context import (
            FinancialsPlanItem,
            MarketDataPlanItem,
            RetrievalPlan,
            SearchPlanItem,
        )

        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL"),
            plan=RetrievalPlan(
                search_queries=[SearchPlanItem(query="AAPL analysis", max_results=3)],
                market_data=[MarketDataPlanItem(ticker="AAPL", period="1y")],
                financials=[
                    FinancialsPlanItem(
                        ticker="AAPL",
                        statement_type=FinancialStatementType.INCOME_STATEMENT,
                    )
                ],
                fetch_company_info_tickers=["AAPL"],
                fetch_analyst_data_tickers=["AAPL"],
            ),
        )
        deps = _make_deps(config)
        result = await retrieve(ctx, deps)
        assert len(result.evidence) >= 4
        sources = [e.source for e in result.evidence]
        assert any("search:" in s for s in sources)
        assert any("market_data:" in s for s in sources)
        assert any("company_info:" in s for s in sources)
        assert any("analyst:" in s for s in sources)

    @pytest.mark.asyncio
    async def test_retrieve_handles_errors_gracefully(self, config: ResearchWorkflowConfig):
        class FailingMarketData:
            def get_market_data(self, *a: Any, **kw: Any) -> MarketDataResponse:
                raise RuntimeError("fail")

            def get_financials(self, *a: Any, **kw: Any) -> FinancialStatementResponse:
                raise RuntimeError("fail")

            def get_analyst_data(self, *a: Any, **kw: Any) -> AnalystResponse:
                raise RuntimeError("fail")

            def get_company_info(self, *a: Any, **kw: Any) -> CompanyInfo:
                raise RuntimeError("fail")

            def get_crypto_data(self, *a: Any, **kw: Any) -> CryptoDataResponse:
                raise RuntimeError("fail")

        from fin_agent.workflows.research.context import RetrievalPlan, SearchPlanItem

        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            plan=RetrievalPlan(
                search_queries=[SearchPlanItem(query="test", max_results=3)],
            ),
        )
        deps = _make_deps(config, market_data=FailingMarketData())
        result = await retrieve(ctx, deps)
        assert len(result.evidence) >= 1


class TestToolExecStage:
    @pytest.mark.asyncio
    async def test_tool_exec_done_immediately(self, config: ResearchWorkflowConfig):
        done_response = LLMResponse(
            message=LLMMessage(role="assistant", content="```done```")
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            evidence=[EvidenceItem(source="search", summary="enough data")],
        )
        deps = _make_deps(config, llm_responses=[done_response])
        result = await tool_exec(ctx, deps)
        assert len(result.tool_calls) == 0


class TestSynthesizeStage:
    @pytest.mark.asyncio
    async def test_synthesize_generates_report(self, config: ResearchWorkflowConfig):
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            evidence=[EvidenceItem(source="search", summary="AAPL data")],
        )
        deps = _make_deps(config, llm_responses=[SYNTHESIZE_RESPONSE])
        result = await synthesize(ctx, deps)
        assert "Research Report" in result.report
        assert len(result.trace) == 1

    @pytest.mark.asyncio
    async def test_synthesize_handles_llm_failure(self, config: ResearchWorkflowConfig):
        class FailingLLM:
            async def chat(self, *a: Any, **kw: Any) -> LLMResponse:
                raise RuntimeError("LLM down")

        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            evidence=[EvidenceItem(source="s", summary="e")],
        )
        deps = StageDeps(
            llm=FailingLLM(),
            search=StubSearch(),
            market_data=StubMarketData(),
            config=config,
        )
        result = await synthesize(ctx, deps)
        assert "failed" in result.report.lower() or "unavailable" in result.report.lower()


class TestReviewStage:
    @pytest.mark.asyncio
    async def test_review_passes(self, config: ResearchWorkflowConfig):
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            report="A good report with evidence.",
        )
        deps = _make_deps(config, llm_responses=[REVIEW_RESPONSE])
        result = await review(ctx, deps)
        assert result.review_passed is True
        assert result.review_feedback != ""

    @pytest.mark.asyncio
    async def test_review_handles_bad_json(self, config: ResearchWorkflowConfig):
        bad_review = LLMResponse(
            message=LLMMessage(role="assistant", content="not json")
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            report="some report",
        )
        deps = _make_deps(config, llm_responses=[bad_review])
        result = await review(ctx, deps)
        assert result.review_passed is True


class TestPersistStage:
    @pytest.mark.asyncio
    async def test_persist_adds_trace(self, config: ResearchWorkflowConfig):
        ctx = ResearchContext(
            run_id="test-id",
            request=ResearchRequest(question="test"),
            evidence=[EvidenceItem(source="s", summary="e")],
        )
        deps = _make_deps(config)
        result = await persist(ctx, deps)
        assert len(result.trace) == 1
        assert result.trace[0].stage == "persist"


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()

        async def my_tool(**kwargs: Any) -> str:
            return "ok"

        registry.register("my_tool", my_tool)
        assert registry.get("my_tool") is my_tool
        assert "my_tool" in registry.available_tools()

    def test_get_unknown_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_tool_schemas(self):
        registry = ToolRegistry()

        async def t1(**kwargs: Any) -> str:
            return ""

        registry.register("alpha", t1)
        registry.register("beta", t1)
        schemas = registry.tool_schemas()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"alpha", "beta"}


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_full_workflow_e2e(self, config: ResearchWorkflowConfig):
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        tool_exec_done = LLMResponse(
            message=LLMMessage(role="assistant", content="```done```")
        )
        llm_responses = [plan_response, tool_exec_done, SYNTHESIZE_RESPONSE, REVIEW_RESPONSE]
        deps = _make_deps(config, llm_responses=llm_responses)
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        result = await execute_workflow(ctx, deps)
        assert result.run_id != ""
        assert len(result.evidence) > 0
        assert result.report != ""
        assert result.review_passed is True
        stage_names = [t.stage for t in result.trace]
        assert "intake" in stage_names
        assert "persist" in stage_names

    @pytest.mark.asyncio
    async def test_workflow_without_review(self):
        config = ResearchWorkflowConfig(enable_review=False, max_tool_calls=3)
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        tool_exec_done = LLMResponse(
            message=LLMMessage(role="assistant", content="```done```")
        )
        llm_responses = [plan_response, tool_exec_done, SYNTHESIZE_RESPONSE]
        deps = _make_deps(config, llm_responses=llm_responses)
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        result = await execute_workflow(ctx, deps)
        stage_names = [t.stage for t in result.trace]
        assert "review" not in stage_names


class TestRegisterStage:
    @pytest.mark.asyncio
    async def test_custom_stage_registration(self):
        from fin_agent.workflows.research.graph import register_stage

        async def custom_stage(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
            ctx.trace.append(TraceRecord(stage="custom", detail="ran"))
            return ctx

        register_stage("custom", custom_stage)
        config = ResearchWorkflowConfig(enable_review=False, max_tool_calls=1)
        plan_resp = LLMResponse(
            message=LLMMessage(
                role="assistant",
                content=json.dumps({
                    "search_queries": [],
                    "market_data": [],
                    "financials": [],
                    "fetch_company_info_tickers": [],
                    "fetch_analyst_data_tickers": [],
                    "fetch_crypto_tickers": [],
                }),
            )
        )
        tool_done = LLMResponse(message=LLMMessage(role="assistant", content="```done```"))
        synth = LLMResponse(message=LLMMessage(role="assistant", content="report"))
        _deps = _make_deps(config, llm_responses=[plan_resp, tool_done, synth])

        from fin_agent.workflows.research.graph import _STAGE_REGISTRY

        assert "custom" in _STAGE_REGISTRY
