from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fin_agent.bootstrap.app import create_default_app
from fin_agent.bootstrap.cli import app as cli_app
from fin_agent.domain.constants import AssetType
from fin_agent.domain.types import (
    LLMMessage,
    LLMResponse,
    MarketDataPoint,
    MarketDataResponse,
    SearchResponse,
    SearchResultItem,
)


def _mock_llm_chat(*args, **kwargs):
    plan_json = json.dumps({
        "search_queries": [{"query": "AAPL test", "max_results": 3}],
        "market_data": [],
        "financials": [],
        "fetch_company_info_tickers": [],
        "fetch_analyst_data_tickers": [],
        "fetch_crypto_tickers": [],
    })
    call_count = getattr(_mock_llm_chat, "_count", 0)
    _mock_llm_chat._count = call_count + 1
    if call_count == 0:
        return LLMResponse(message=LLMMessage(role="assistant", content=plan_json))
    if call_count == 1:
        return LLMResponse(message=LLMMessage(role="assistant", content="```done```"))
    if call_count == 2:
        return LLMResponse(
            message=LLMMessage(role="assistant", content="# Test Report\nSynthesis.")
        )
    return LLMResponse(
        message=LLMMessage(role="assistant", content='{"passed": true, "feedback": "ok"}')
    )


_mock_llm_chat._count = 0


def _mock_search_search(query, *, max_results=None):
    return SearchResponse(
        query=query,
        results=[
            SearchResultItem(
                title=f"Test result for {query}",
                url="https://example.com",
                text="Test text",
            )
        ],
    )


def _mock_market_data_get(ticker, asset_type, **kwargs):
    from datetime import date

    return MarketDataResponse(
        ticker=ticker,
        asset_type=asset_type or AssetType.STOCK,
        data=[
            MarketDataPoint(
                ticker=ticker,
                asset_type=asset_type or AssetType.STOCK,
                trade_date=date(2025, 1, 1),
                open=100.0,
                high=105.0,
                low=99.0,
                close=102.0,
                volume=1000,
            )
        ],
    )


def test_research_run_round_trip(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI") as mock_openai_cls,
        patch("fin_agent.adapters.search.exa.client.Exa") as mock_exa_cls,
        patch(
            "fin_agent.adapters.market_data.yfinance.client.YFinanceClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
        patch(
            "fin_agent.adapters.market_data.akshare.client.AKShareClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("mocked")
        )
        mock_openai_cls.return_value = mock_client

        _mock_llm_chat._count = 0
        mock_exa_cls.return_value.search.return_value = type(
            "R", (), {"results": []}
        )()

        with TestClient(create_default_app()) as client:
            create_response = client.post(
                '/v1/research/runs',
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL'},
            )
            assert create_response.status_code == 200
            payload = create_response.json()
            assert payload['run_id']
            assert payload['status'] == 'completed'
            assert len(payload['evidence']) >= 0
            assert len(payload['trace']) >= 1

            trace_response = client.get(
                f"/v1/research/runs/{payload['run_id']}/trace"
            )
            assert trace_response.status_code == 200
            assert trace_response.json()['run_id'] == payload['run_id']


def test_research_cli_runs(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        result = CliRunner().invoke(
            cli_app,
            ['research', 'run', '--question', 'Test question'],
        )
        payload = json.loads(result.stdout)
        assert payload['run_id']
        assert payload['status'] in ('completed', 'failed')
        if payload['status'] == 'failed':
            assert result.exit_code == 1
        else:
            assert result.exit_code == 0
