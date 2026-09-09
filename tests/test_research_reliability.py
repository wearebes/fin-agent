"""Regression tests for evidence integrity, bounded execution and honest outcomes."""

from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import AsyncMock, Mock

import pytest
from test_research_workflow import PLAN_JSON, REVIEW_RESPONSE, _make_deps

from fin_agent.domain.constants import EnvironmentName, FinancialStatementType, RunStatus
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    EvidenceItem,
    FinancialStatementRecord,
    FinancialStatementResponse,
    LLMMessage,
    LLMResponse,
    ResearchRequest,
    SearchResponse,
    SearchResultItem,
)
from fin_agent.services.research import ResearchService
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import FinancialsPlanItem, ResearchContext, SearchPlanItem
from fin_agent.workflows.research.evidence import compact_records, render_evidence
from fin_agent.workflows.research.stages.core import retrieve
from fin_agent.workflows.research.stages.pipeline import review, synthesize, tool_exec
from fin_agent.workflows.research.stages.tools import build_default_tool_registry


@pytest.fixture
def config():
    return ResearchWorkflowConfig(max_tool_calls=3, max_iterations=2, evidence_limit=20)


def response(text: str) -> LLMResponse:
    return LLMResponse(message=LLMMessage(role="assistant", content=text))


def context() -> ResearchContext:
    return ResearchContext(
        request=ResearchRequest(question="Compare annual revenue", ticker="AAPL")
    )


@pytest.mark.asyncio
async def test_financial_values_reach_writer_and_reviewer(config):
    ctx = context()
    ctx.plan.financials = [FinancialsPlanItem(ticker="AAPL")]
    deps = _make_deps(config)
    ctx = await retrieve(ctx, deps)
    records = json.loads(ctx.evidence[0].summary)
    assert records[0]["total_revenue"] == 394328000000.0
    assert records[0]["net_income"] == 99803000000.0
    captured = []

    async def chat(messages, **kwargs):
        captured.append(messages[-1].content)
        return response("Report with supported values") if len(captured) == 1 else REVIEW_RESPONSE

    deps.llm.chat = chat
    ctx = await synthesize(ctx, deps)
    await review(ctx, deps)
    for prompt in captured:
        assert "394328000000.0" in prompt
        assert "99803000000.0" in prompt
        assert "financials:AAPL" in prompt


@pytest.mark.asyncio
async def test_retrieval_and_financial_tool_keep_same_latest_periods(config):
    records = [
        FinancialStatementRecord(
            ticker="AAPL", statement_type=FinancialStatementType.INCOME_STATEMENT,
            fiscal_year=year, fiscal_quarter=quarter, total_revenue=year * 10 + (quarter or 0),
        )
        for year in [2024, 2023, 2025]
        for quarter in [None, 2, 1]
    ]
    deps = _make_deps(config)
    deps.market_data.get_financials = Mock(return_value=FinancialStatementResponse(
        ticker="AAPL", statement_type=FinancialStatementType.INCOME_STATEMENT, data=records,
    ))
    ctx = context()
    ctx.plan.financials = [FinancialsPlanItem(ticker="AAPL")]
    await retrieve(ctx, deps)
    tool = build_default_tool_registry(deps.search, deps.market_data).get("financials")
    result = await tool(ticker="AAPL")
    assert result == ctx.evidence[0].summary
    actual = json.loads(result)
    assert [(r["fiscal_year"], r.get("fiscal_quarter")) for r in actual] == [
        (2025, 2), (2025, 1), (2025, None), (2024, 2),
        (2024, 1), (2024, None), (2023, 2), (2023, 1),
    ]
    assert actual[0]["total_revenue"] == 20252
    assert records[0].fiscal_year == 2024


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_text",
    [
        '```tool_call\n{"name":"nonexistent","arguments":{}}\n```',
        '```tool_call\n{"name":"search","arguments":{"unexpected":"value"}}\n```',
    ],
)
async def test_rejected_tools_cannot_bypass_iteration_limit(config, tool_text):
    deps = _make_deps(config)
    deps.llm.chat = AsyncMock(return_value=response(tool_text))
    ctx = await tool_exec(context(), deps)
    assert deps.llm.chat.await_count == config.max_iterations
    assert ctx.iteration == config.max_iterations
    assert not ctx.tool_calls
    assert any("budget reached" in trace.detail for trace in ctx.trace)


@pytest.mark.asyncio
async def test_duplicate_call_does_not_repeat_provider_io(config):
    deps = _make_deps(config)
    deps.llm.chat = AsyncMock(
        return_value=response(
            '```tool_call\n{"name":"financials","arguments":{"ticker":"AAPL"}}\n```'
        )
    )
    ctx = await tool_exec(context(), deps)
    assert len(ctx.tool_calls) == 1
    assert "394328000000.0" in ctx.evidence[0].summary
    assert any("Repeated identical" in trace.detail for trace in ctx.trace)


@pytest.mark.asyncio
async def test_tool_evidence_is_not_cut_at_500_characters(config):
    deps = _make_deps(config)
    deps.search.search = lambda query, **kwargs: SearchResponse(
        query=query,
        results=[
            SearchResultItem(
                title="Long evidence",
                url="https://example.com",
                text="x" * 800 + " supported value: 12345",
            ),
        ],
    )
    deps.llm.chat = AsyncMock(
        side_effect=[
            response('```tool_call\n{"name":"search","arguments":{"query":"example"}}\n```'),
            response("```done```"),
        ]
    )
    ctx = await tool_exec(context(), deps)
    assert "12345" in ctx.evidence[0].summary
    assert json.loads(ctx.evidence[0].summary)[0]["title"] == "Long evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["", "not JSON", '{"passed":"false"}', '{"passed":false}'])
async def test_review_fails_closed(config, payload):
    deps = _make_deps(config, llm_responses=[response(payload)])
    ctx = context()
    ctx.report = "An unverified report"
    ctx = await review(ctx, deps)
    assert ctx.review_passed is False
    assert ctx.failed_stages == ["review"]


@pytest.mark.asyncio
async def test_no_evidence_skips_paid_synthesis_call(config):
    deps = _make_deps(config)
    deps.llm.chat = AsyncMock()
    ctx = await synthesize(context(), deps)
    deps.llm.chat.assert_not_awaited()
    assert ctx.failed_stages == ["synthesize"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report,review_text,expected",
    [
        ("Valid report", '{"passed":true}', RunStatus.COMPLETED),
        ("Valid report", '{"passed":false}', RunStatus.FAILED),
        ("", '{"passed":true}', RunStatus.FAILED),
    ],
)
async def test_service_uses_outcome_not_word_failed(config, report, review_text, expected):
    deps = _make_deps(
        config,
        llm_responses=[
            response(PLAN_JSON),
            response("```done```"),
            response(report),
            response(review_text),
        ],
    )
    service = ResearchService(EnvironmentName.TEST, {}, InMemoryRunStore(), deps)
    result = await service.run(ResearchRequest(question="Why have past strategies failed?"))
    assert result.status == expected
    assert service.get_run(result.run_id) == result


@pytest.mark.asyncio
async def test_search_does_not_block_event_loop(config):
    deps = _make_deps(config)
    original = deps.search.search
    release = threading.Event()
    heartbeat_observed = []

    def slow_search(query, **kwargs):
        heartbeat_observed.append(release.wait(timeout=1))
        return original(query, **kwargs)

    async def heartbeat():
        await asyncio.sleep(0.01)
        release.set()

    deps.search.search = slow_search
    ctx = context()
    ctx.plan.search_queries = [SearchPlanItem(query="example")]
    await asyncio.gather(retrieve(ctx, deps), heartbeat())
    assert heartbeat_observed == [True]


def test_evidence_budget_keeps_valid_complete_records():
    records = [{"year": year, "revenue": 123456789.01} for year in range(2000, 2030)]
    payload = compact_records(records, limit=200)
    parsed = json.loads(payload)
    assert len(payload) <= 200
    assert parsed["omitted_records"] + len(parsed["records"]) == 30
    assert all(row["revenue"] == 123456789.01 for row in parsed["records"])
    assert "source" in render_evidence([EvidenceItem(source="test", summary="Evidence")])


def test_large_record_cannot_hide_later_usable_evidence():
    records = [{"text": "x" * 1000}, {"year": 2025, "cash_flow": 123456789.01}]
    parsed = json.loads(compact_records(records, limit=150))
    assert parsed["records"] == [records[1]]
    assert parsed["omitted_records"] == 1
    assert records[0]["text"] == "x" * 1000


def test_new_tool_evidence_reaches_next_decision_when_old_context_is_full():
    old = EvidenceItem(source="old", summary="x" * 500)
    newest = EvidenceItem(source="tool:search", summary="New source: verified 2025 cash flow")
    original = [old, newest, newest]
    payload = json.loads(render_evidence(original, limit=180))
    assert payload["records"] == [newest.model_dump()]
    assert payload["omitted_records"] == 1
    assert original == [old, newest, newest]


@pytest.mark.asyncio
async def test_synthesis_timeout_is_visible_and_never_reported_as_generated(config):
    ctx = context()
    ctx.request.lang = "zh"
    ctx.evidence = [EvidenceItem(source="annual report", summary="Original financial evidence")]
    deps = _make_deps(config)
    deps.llm.chat = AsyncMock(side_effect=TimeoutError("provider-private-data"))
    await synthesize(ctx, deps)
    assert "模型响应超时" in ctx.report
    assert "provider-private-data" not in ctx.report
    assert ctx.failed_stages == ["synthesize"]
    assert not any("Generated report" in trace.detail for trace in ctx.trace)
    assert ctx.evidence[0].summary == "Original financial evidence"
    deps.llm.chat.assert_awaited_once()


def test_tools_expose_and_enforce_parameter_schemas(config):
    deps = _make_deps(config)
    registry = build_default_tool_registry(deps.search, deps.market_data)
    schemas = {tool["name"]: tool["parameters"] for tool in registry.tool_schemas()}
    assert schemas["financials"]["required"] == ["ticker"]
    assert "statement_type" in schemas["financials"]["properties"]
    with pytest.raises(ValueError):
        registry.validate_arguments("search", {"query": "", "max_results": 10000})


@pytest.mark.asyncio
async def test_empty_company_and_analyst_metadata_are_not_evidence(config):
    deps = _make_deps(config)
    deps.market_data.get_company_info = lambda ticker: CompanyInfo(ticker=ticker)
    deps.market_data.get_analyst_data = lambda ticker: AnalystResponse(ticker=ticker)
    ctx = context()
    ctx.plan.fetch_company_info_tickers = ["AAPL"]
    ctx.plan.fetch_analyst_data_tickers = ["AAPL"]
    ctx = await retrieve(ctx, deps)
    assert not ctx.evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["company_info", "analyst"])
async def test_empty_metadata_tool_results_are_not_evidence(config, tool_name):
    deps = _make_deps(config)
    deps.market_data.get_company_info = lambda ticker: CompanyInfo(ticker=ticker)
    deps.market_data.get_analyst_data = lambda ticker: AnalystResponse(ticker=ticker)
    deps.llm.chat = AsyncMock(
        side_effect=[
            response(
                "```tool_call\n"
                + json.dumps({"name": tool_name, "arguments": {"ticker": "AAPL"}})
                + "\n```"
            ),
            response("```done```"),
        ]
    )
    ctx = await tool_exec(context(), deps)
    assert not ctx.evidence
