from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest
from test_research_reliability import context, response
from test_research_workflow import _make_deps

from fin_agent.adapters.market_data.akshare.client import AKShareClient
from fin_agent.adapters.search.stock_news import stock_news
from fin_agent.adapters.search.tavily.client import TavilySearchClient
from fin_agent.domain.constants import DataFrequency, FinancialStatementType
from fin_agent.domain.types import EvidenceItem, LLMMessage, LLMResponse
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.stages.pipeline import synthesize, tool_exec
from fin_agent.workflows.research.stages.tools import build_default_tool_registry


def test_interim_financials_do_not_mix_ytd_and_standalone_quarters():
    from test_market_data_router import _financial_resp

    from fin_agent.adapters.market_data.router import MarketDataRouter

    with (
        patch("fin_agent.adapters.market_data.router.YFinanceClient") as yf,
        patch("fin_agent.adapters.market_data.router.AKShareClient") as ak,
    ):
        yf.return_value.get_financials.return_value = _financial_resp("002214.SZ", 10, 2)
        ak.return_value.get_financials.return_value = _financial_resp("002214", 30, None)
        result = MarketDataRouter().get_financials(
            "002214.SZ",
            FinancialStatementType.INCOME_STATEMENT,
            frequency=DataFrequency.QUARTERLY,
        )
    assert result.data[0].total_revenue == 30
    assert result.data[0].net_income is None


@pytest.mark.asyncio
async def test_illustrated_retrieval_adds_annuals_beside_requested_interims():
    from fin_agent.domain.types import FinancialsPlanItem
    from fin_agent.workflows.research.stages.core import retrieve

    ctx = context()
    ctx.request.ticker = "AAPL"
    ctx.request.template = "illustrated_research"
    ctx.plan.financials = [
        FinancialsPlanItem(ticker="AAPL", statement_type=s, frequency=DataFrequency.QUARTERLY)
        for s in FinancialStatementType
    ]
    await retrieve(ctx, _make_deps(ResearchWorkflowConfig()))
    assert len([f for f in ctx.plan.financials if f.frequency == DataFrequency.YEARLY]) == 3


def test_real_financial_field_names_and_annual_period_filter():
    frame = pd.DataFrame(
        [
            {"REPORT_DATE": "2026-06-30", "TOTAL_OPERATE_INCOME": 50, "NETPROFIT": -4},
            {"REPORT_DATE": "2025-12-31", "TOTAL_OPERATE_INCOME": 120, "NETPROFIT": -8},
            {"REPORT_DATE": "2024-12-31", "TOTAL_OPERATE_INCOME": 100, "NETPROFIT": -10},
        ]
    )
    with patch(
        "fin_agent.adapters.market_data.akshare.client.ak.stock_profit_sheet_by_report_em",
        return_value=frame,
    ) as fetch:
        result = AKShareClient().get_financials("002214", FinancialStatementType.INCOME_STATEMENT)
    fetch.assert_called_once_with(symbol="SZ002214")
    assert [(r.fiscal_year, r.total_revenue, r.net_income) for r in result.data] == [
        (2025, 120, -8),
        (2024, 100, -10),
    ]
    assert result.currency == "CNY"


@pytest.mark.parametrize(
    "primary", [None, pd.DataFrame(), pd.DataFrame([["股票简称", "大立科技"]])]
)
def test_company_fallback_checks_symbol_and_reads_description(primary):
    payload = {
        "jbzl": [
            {
                "SECURITY_CODE": "002214",
                "ORG_NAME": "大立科技",
                "ORG_PROFILE": "红外产品",
                "EMP_NUM": 860,
            }
        ]
    }
    with (
        patch(
            "fin_agent.adapters.market_data.akshare.client.ak.stock_individual_info_em",
            return_value=primary,
        ),
        patch(
            "fin_agent.adapters.market_data.akshare.client.requests.get",
            return_value=Mock(json=lambda: payload),
        ),
    ):
        result = AKShareClient().get_company_info("002214")
    assert result.name == "大立科技" and result.description == "红外产品"


def test_news_dates_links_and_headline_only_scope():
    html = (
        '<div class="datelist">2026-09-10 18:00 '
        '<a href="https://finance.sina.com.cn/roll/event.shtml">Company event</a>'
        "<br/>2026-09-11 15:00 "
        '<a href="https://finance.sina.com.cn/stock/aiassist/example">AI opinion</a></div>'
    )
    with patch("fin_agent.adapters.search.stock_news.requests.get", return_value=Mock(text=html)):
        result = stock_news("002214.SZ")
    assert len(result.results) == 1
    assert "2026-09-10" in result.results[0].text
    assert "headline only" in result.results[0].text
    assert not stock_news("000660.KS").results


@pytest.mark.parametrize("available", [True, False])
def test_news_reads_original_article_or_retains_headline(available):
    import requests

    listing = Mock(
        text='<div class="datelist">2026-09-10 18:00 '
        '<a href="https://finance.sina.com.cn/roll/event.shtml">Event</a></div>'
    )
    article = Mock(
        status_code=200,
        apparent_encoding="utf-8",
        text='<div id="artibody">Verified article<script>ignore me</script></div>',
    )
    with patch(
        "fin_agent.adapters.search.stock_news.requests.get",
        side_effect=[listing, article if available else requests.Timeout()],
    ) as fetch:
        result = stock_news("002214")
    assert ("Verified article" in result.results[0].text) == available
    assert "ignore me" not in result.results[0].text
    assert ("headline only" in result.results[0].text) != available
    assert fetch.call_args.kwargs["allow_redirects"] is False


def test_unconfigured_search_is_not_advertised_to_model():
    registry = build_default_tool_registry(TavilySearchClient(), Mock())
    assert "search" not in registry.available_tools()


@pytest.mark.asyncio
async def test_model_error_category_is_retained_without_error_body():
    deps = _make_deps(ResearchWorkflowConfig())
    deps.llm.chat = AsyncMock(
        return_value=LLMResponse(
            message=LLMMessage(role="assistant", content=""), error_code="APITimeoutError"
        )
    )
    ctx = context()
    ctx.evidence = [EvidenceItem(source="data", summary="verified")]
    await synthesize(ctx, deps)
    assert "超时" in ctx.report
    assert "APITimeoutError" in ctx.trace[-1].detail
    deps.llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_rounds_stop_without_false_evidence():
    deps = _make_deps(ResearchWorkflowConfig())
    deps.tool_registry.register("empty", AsyncMock(return_value="[]"))
    deps.llm.chat = AsyncMock(
        side_effect=[
            response('```tool_call\n{"name":"empty","arguments":{"q":1}}\n```'),
            response('```tool_call\n{"name":"empty","arguments":{"q":2}}\n```'),
        ]
    )
    ctx = await tool_exec(context(), deps)
    assert not ctx.evidence
    assert deps.llm.chat.await_count == 2
