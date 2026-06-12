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
from fin_agent.workflows.research.graph import (
    build_resume_stages,
    build_stage_plan,
    execute_workflow,
)
from fin_agent.workflows.research.stages import StageDeps, ToolRegistry
from fin_agent.workflows.research.stages.core import intake, plan, retrieve
from fin_agent.workflows.research.stages.pipeline import (
    persist,
    review,
    synthesize,
    tool_exec,
)
from fin_agent.workflows.research.stages.tools import build_default_tool_registry


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
        tools: list | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        # Default terminal response: no tool calls -> tool-exec loop ends.
        return LLMResponse(
            message=LLMMessage(role="assistant", content="No further tools needed.")
        )


class _CapturingLLM(StubLLM):
    """Stub LLM that records every `messages` list it is called with, in order.

    The skill-injection tests below only care about "what system prompt did
    this stage build", and all need the same capture — sharing it here avoids
    five near-identical inline `CapturingLLM` redefinitions.
    """

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        super().__init__(responses)
        self.calls: list[list[LLMMessage]] = []

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        self.calls.append(messages)
        return await super().chat(messages, **kwargs)


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
    resolved_search = search or StubSearch()
    resolved_market_data = market_data or StubMarketData()
    return StageDeps(
        llm=StubLLM(llm_responses),
        search=resolved_search,
        market_data=resolved_market_data,
        tool_registry=build_default_tool_registry(
            resolved_search, resolved_market_data
        ),
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

    def test_skill_instructions_defaults_to_empty(self):
        # Empty means "no skill selected, or it resolved to a body-less
        # structural skill" — both deliberate no-ops for prompt injection.
        ctx = ResearchContext(request=ResearchRequest(question="test"))
        assert ctx.skill_instructions == ""

    def test_skill_instructions_round_trips(self):
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            skill_instructions="Follow the valuation playbook.",
        )
        assert ctx.skill_instructions == "Follow the valuation playbook."

    def test_research_context_round_trips_through_json(self):
        from fin_agent.workflows.research.context import (
            FinancialsPlanItem,
            MarketDataPlanItem,
            RetrievalPlan,
            SearchPlanItem,
        )

        ctx = ResearchContext(
            run_id="round-trip-id",
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
            report="# Draft report",
            review_passed=True,
            review_feedback="Looks solid.",
            iteration=2,
            metadata={"custom_key": "custom_value"},
        )

        restored = ResearchContext.model_validate_json(ctx.model_dump_json())
        assert restored.model_dump() == ctx.model_dump()


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


class TestBuildResumeStages:
    def test_build_resume_stages_with_review(self, config: ResearchWorkflowConfig):
        stages = build_resume_stages(config)
        expected = ["retrieve", "tool-exec", "synthesize", "review", "persist"]
        assert stages == expected

    def test_build_resume_stages_without_review(self):
        cfg = ResearchWorkflowConfig(enable_review=False)
        stages = build_resume_stages(cfg)
        expected = ["retrieve", "tool-exec", "synthesize", "persist"]
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

    @pytest.mark.asyncio
    async def test_plan_prompt_includes_tool_catalog(
        self, config: ResearchWorkflowConfig
    ):
        captured: dict[str, list] = {}

        class CapturingLLM(StubLLM):
            async def chat(self, messages, **kwargs):
                captured["messages"] = messages
                return await super().chat(messages, **kwargs)

        ctx = ResearchContext(request=ResearchRequest(question="Analyze AAPL"))
        deps = _make_deps(config)
        deps.llm = CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content=PLAN_JSON))]
        )
        await plan(ctx, deps)

        system_prompt = captured["messages"][0].content
        # The plan stage now sees what the execute stage can actually fetch.
        for tool_name in deps.tool_registry.available_tools():
            assert tool_name in system_prompt


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
        # No tool_calls -> the loop terminates immediately (structured judgment,
        # replacing the old "```done```" string match).
        done_response = LLMResponse(
            message=LLMMessage(role="assistant", content="I have enough evidence.")
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="test"),
            evidence=[EvidenceItem(source="search", summary="enough data")],
        )
        deps = _make_deps(config, llm_responses=[done_response])
        result = await tool_exec(ctx, deps)
        assert len(result.tool_calls) == 0
        details = [t.detail for t in result.trace if t.stage == "tool-exec"]
        assert any("no further tool calls" in d for d in details)

    @pytest.mark.asyncio
    async def test_tool_exec_parallel_then_final(
        self, config: ResearchWorkflowConfig
    ):
        from fin_agent.domain.types import ToolCall
        from fin_agent.workflows.research.context import (
            MarketDataPlanItem,
            RetrievalPlan,
            SearchPlanItem,
        )

        # Round 1: model requests two tools at once. Round 2: final text answer.
        parallel_round = LLMResponse(
            message=LLMMessage(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_a",
                        name="market_data",
                        arguments={"ticker": "AAPL"},
                    ),
                    ToolCall(
                        id="call_b",
                        name="financials",
                        arguments={"ticker": "AAPL"},
                    ),
                ],
            )
        )
        final_round = LLMResponse(
            message=LLMMessage(role="assistant", content="Sufficient evidence gathered.")
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL"),
            plan=RetrievalPlan(
                search_queries=[SearchPlanItem(query="AAPL earnings", max_results=3)],
                market_data=[MarketDataPlanItem(ticker="AAPL", period="1y")],
            ),
        )
        deps = _make_deps(config, llm_responses=[parallel_round, final_round])
        result = await tool_exec(ctx, deps)

        # (a) Both tool calls were executed and recorded.
        assert len(result.tool_calls) == 2
        recorded = {tc.tool_name for tc in result.tool_calls}
        assert recorded == {"market_data", "financials"}

        # (b) Structured trace shows the parallel request + each result line.
        details = [t.detail for t in result.trace if t.stage == "tool-exec"]
        assert any("requested 2 tool call(s) in parallel" in d for d in details)
        assert any(d.startswith("market_data →") for d in details)
        assert any(d.startswith("financials →") for d in details)

        # (c) Loop terminated structurally on the no-tool-calls round.
        assert any("no further tool calls" in d for d in details)

    @pytest.mark.asyncio
    async def test_tool_exec_seed_message_includes_plan_summary(
        self, config: ResearchWorkflowConfig
    ):
        from fin_agent.workflows.research.context import (
            RetrievalPlan,
            SearchPlanItem,
        )
        from fin_agent.workflows.research.stages.pipeline import _summarize_plan

        captured: dict[str, list] = {}

        class CapturingLLM(StubLLM):
            async def chat(self, messages, **kwargs):
                captured["messages"] = messages
                return await super().chat(messages, **kwargs)

        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            plan=RetrievalPlan(
                search_queries=[SearchPlanItem(query="AAPL guidance", max_results=4)],
            ),
        )
        deps = _make_deps(config)
        deps.llm = CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content="done"))]
        )
        await tool_exec(ctx, deps)

        seed_user = captured["messages"][1].content
        assert _summarize_plan(ctx.plan) in seed_user
        assert "AAPL guidance" in seed_user


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
        _search = StubSearch()
        _market_data = StubMarketData()
        deps = StageDeps(
            llm=FailingLLM(),
            search=_search,
            market_data=_market_data,
            tool_registry=build_default_tool_registry(_search, _market_data),
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


class TestSkillInstructionInjection:
    """`ResearchContext.skill_instructions`, once resolved by the dispatcher,
    must be prepended verbatim to the system prompt of every LLM-facing
    stage — and must be a complete no-op (prompt byte-for-byte unchanged)
    when empty, which is the default for "no skill selected"."""

    SKILL_MARKER = "SKILL-MARKER: focus on valuation discipline."

    @pytest.mark.asyncio
    async def test_plan_prepends_instructions_when_present(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content=PLAN_JSON))]
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            skill_instructions=self.SKILL_MARKER,
        )
        deps = _make_deps(config)
        deps.llm = llm
        await plan(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith(self.SKILL_MARKER + "\n\n")
        assert "research planning assistant" in system_prompt

    @pytest.mark.asyncio
    async def test_plan_prompt_untouched_without_skill(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content=PLAN_JSON))]
        )
        ctx = ResearchContext(request=ResearchRequest(question="Analyze AAPL"))
        assert ctx.skill_instructions == ""
        deps = _make_deps(config)
        deps.llm = llm
        await plan(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith("You are a research planning assistant")
        assert self.SKILL_MARKER not in system_prompt

    @pytest.mark.asyncio
    async def test_tool_exec_prepends_instructions_when_present(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content="No further tools needed."))]
        )
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            skill_instructions=self.SKILL_MARKER,
        )
        deps = _make_deps(config)
        deps.llm = llm
        await tool_exec(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith(self.SKILL_MARKER + "\n\n")
        assert "financial research assistant with access to tools" in system_prompt

    @pytest.mark.asyncio
    async def test_tool_exec_prompt_untouched_without_skill(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM(
            [LLMResponse(message=LLMMessage(role="assistant", content="No further tools needed."))]
        )
        ctx = ResearchContext(request=ResearchRequest(question="Analyze AAPL"))
        deps = _make_deps(config)
        deps.llm = llm
        await tool_exec(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith("You are a financial research assistant")
        assert self.SKILL_MARKER not in system_prompt

    @pytest.mark.asyncio
    async def test_synthesize_prepends_instructions_when_present(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM([SYNTHESIZE_RESPONSE])
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            skill_instructions=self.SKILL_MARKER,
            evidence=[EvidenceItem(source="search", summary="AAPL data")],
        )
        deps = _make_deps(config)
        deps.llm = llm
        await synthesize(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith(self.SKILL_MARKER + "\n\n")
        assert "senior financial research analyst" in system_prompt

    @pytest.mark.asyncio
    async def test_synthesize_prompt_untouched_without_skill(
        self, config: ResearchWorkflowConfig
    ):
        llm = _CapturingLLM([SYNTHESIZE_RESPONSE])
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL"),
            evidence=[EvidenceItem(source="search", summary="AAPL data")],
        )
        deps = _make_deps(config)
        deps.llm = llm
        await synthesize(ctx, deps)

        system_prompt = llm.calls[0][0].content
        assert system_prompt.startswith("You are a senior financial research analyst")
        assert self.SKILL_MARKER not in system_prompt


class TestResearchServiceSkillResolution:
    """`ResearchService.run` is the seam that turns the API-level
    `request.selected_skill` (an opaque catalog name) into
    `ctx.skill_instructions` (the resolved text every stage injects). This
    exercises that resolution directly — independent of the full stage graph,
    which `TestSkillInstructionInjection` above already covers."""

    @pytest.mark.asyncio
    async def test_run_resolves_selected_skill_into_context_instructions(
        self, config: ResearchWorkflowConfig, monkeypatch: pytest.MonkeyPatch
    ):
        from fin_agent.domain.constants import EnvironmentName
        from fin_agent.services import research as research_module
        from fin_agent.services.research import ResearchService
        from fin_agent.services.skill_router import SkillDispatcher
        from fin_agent.skills.manifest import SkillCatalog, SkillManifest
        from fin_agent.storage.run_store import InMemoryRunStore

        catalog = SkillCatalog()
        catalog.register(SkillManifest(name="valuation", body="Valuation guidance body."))
        catalog.register(SkillManifest(name="research", body=""))
        dispatcher = SkillDispatcher(catalog)

        captured: dict[str, ResearchContext] = {}

        async def fake_execute_workflow(ctx, deps, **kwargs):
            captured["ctx"] = ctx
            return ctx

        monkeypatch.setattr(research_module, "execute_workflow", fake_execute_workflow)

        service = ResearchService(
            environment=EnvironmentName.TEST,
            providers={},
            run_store=InMemoryRunStore(),
            deps=_make_deps(config),
            skill_dispatcher=dispatcher,
        )

        await service.run(
            ResearchRequest(question="Analyze AAPL", selected_skill="valuation")
        )
        assert captured["ctx"].skill_instructions == "Valuation guidance body."

        await service.run(
            ResearchRequest(question="Analyze AAPL", selected_skill="research")
        )
        assert captured["ctx"].skill_instructions == ""

        await service.run(
            ResearchRequest(question="Analyze AAPL", selected_skill="not-a-real-skill")
        )
        assert captured["ctx"].skill_instructions == ""

        await service.run(ResearchRequest(question="Analyze AAPL"))
        assert captured["ctx"].skill_instructions == ""


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

    def test_register_tool_definition_carries_schema(self):
        from fin_agent.domain.types import ToolDefinition

        registry = ToolRegistry()

        async def t1(**kwargs: Any) -> str:
            return ""

        schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        registry.register(
            ToolDefinition(name="search", description="Search.", input_schema=schema),
            t1,
        )
        defs = registry.definitions()
        assert len(defs) == 1
        assert defs[0].name == "search"
        assert defs[0].input_schema == schema
        # Legacy accessors still work on the new form.
        assert registry.get("search") is t1
        assert registry.available_tools() == ["search"]

    def test_to_openai_tools_shape(self):
        search = StubSearch()
        market_data = StubMarketData()
        registry = build_default_tool_registry(search, market_data)
        openai_tools = registry.to_openai_tools()
        assert len(openai_tools) == len(registry.available_tools())
        first = openai_tools[0]
        assert first["type"] == "function"
        assert "name" in first["function"]
        assert "parameters" in first["function"]
        # The search tool exposes a real JSON Schema with a required 'query'.
        by_name = {t["function"]["name"]: t for t in openai_tools}
        assert "query" in by_name["search"]["function"]["parameters"]["properties"]

    def test_merge_brings_in_external_tools(self):
        from fin_agent.domain.types import ToolDefinition

        base = ToolRegistry()
        other = ToolRegistry()

        async def t1(**kwargs: Any) -> str:
            return "x"

        other.register(
            ToolDefinition(name="mcp_tool", description="From MCP.", source="mcp:demo"),
            t1,
        )
        base.merge(other)
        assert "mcp_tool" in base.available_tools()
        assert base.get("mcp_tool") is t1


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_full_workflow_e2e(self, config: ResearchWorkflowConfig):
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        tool_exec_done = LLMResponse(
            message=LLMMessage(role="assistant", content="Sufficient evidence gathered.")
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
            message=LLMMessage(role="assistant", content="Sufficient evidence gathered.")
        )
        llm_responses = [plan_response, tool_exec_done, SYNTHESIZE_RESPONSE]
        deps = _make_deps(config, llm_responses=llm_responses)
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        result = await execute_workflow(ctx, deps)
        stage_names = [t.stage for t in result.trace]
        assert "review" not in stage_names

    @pytest.mark.asyncio
    async def test_execute_workflow_runs_subset_of_stages(
        self, config: ResearchWorkflowConfig
    ):
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        deps = _make_deps(config, llm_responses=[plan_response])
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        result = await execute_workflow(ctx, deps, stages=["intake", "plan"])
        stage_names = {t.stage for t in result.trace}
        assert stage_names == {"intake", "plan"}
        assert "retrieve" not in stage_names
        assert "tool-exec" not in stage_names
        assert "synthesize" not in stage_names
        assert "review" not in stage_names
        assert "persist" not in stage_names
        assert result.report == ""

    @pytest.mark.asyncio
    async def test_execute_workflow_stages_none_runs_full_plan(
        self, config: ResearchWorkflowConfig
    ):
        plan_response = LLMResponse(
            message=LLMMessage(role="assistant", content=PLAN_JSON)
        )
        tool_exec_done = LLMResponse(
            message=LLMMessage(role="assistant", content="Sufficient evidence gathered.")
        )
        llm_responses = [plan_response, tool_exec_done, SYNTHESIZE_RESPONSE, REVIEW_RESPONSE]
        deps = _make_deps(config, llm_responses=llm_responses)
        ctx = ResearchContext(
            request=ResearchRequest(question="Analyze AAPL", ticker="AAPL")
        )
        result = await execute_workflow(ctx, deps)
        stages_seen: list[str] = []
        for t in result.trace:
            if t.stage not in stages_seen:
                stages_seen.append(t.stage)
        assert stages_seen == build_stage_plan(deps.config)


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
        tool_done = LLMResponse(
            message=LLMMessage(role="assistant", content="Sufficient evidence gathered.")
        )
        synth = LLMResponse(message=LLMMessage(role="assistant", content="report"))
        _deps = _make_deps(config, llm_responses=[plan_resp, tool_done, synth])

        from fin_agent.workflows.research.graph import _STAGE_REGISTRY

        assert "custom" in _STAGE_REGISTRY
