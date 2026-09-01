from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fin_agent.adapters.llm.openai.client import OpenAIClient
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
        return LLMResponse(message=LLMMessage(role="assistant", content="Sufficient evidence gathered."))
    if call_count == 2:
        return LLMResponse(
            message=LLMMessage(role="assistant", content="# Test Report\nSynthesis.")
        )
    return LLMResponse(
        message=LLMMessage(role="assistant", content='{"passed": true, "feedback": "ok"}')
    )


_mock_llm_chat._count = 0


def _mock_llm_chat_with_tickers(*args, **kwargs):
    plan_json = json.dumps({
        "search_queries": [{"query": "AAPL test", "max_results": 3}],
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
    call_count = getattr(_mock_llm_chat_with_tickers, "_count", 0)
    _mock_llm_chat_with_tickers._count = call_count + 1
    if call_count == 0:
        return LLMResponse(message=LLMMessage(role="assistant", content=plan_json))
    if call_count == 1:
        return LLMResponse(message=LLMMessage(role="assistant", content="Sufficient evidence gathered."))
    if call_count == 2:
        return LLMResponse(
            message=LLMMessage(role="assistant", content="# Test Report\nSynthesis.")
        )
    return LLMResponse(
        message=LLMMessage(role="assistant", content='{"passed": true, "feedback": "ok"}')
    )


_mock_llm_chat_with_tickers._count = 0


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


def _make_search_spy(captured: list[str]):
    def _spy(self, query, *, max_results=None):
        captured.append(query)
        return _mock_search_search(query, max_results=max_results)

    return _spy


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


def test_plan_mode_returns_awaiting_approval_with_plan(monkeypatch) -> None:
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
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL', 'mode': 'plan'},
            )
            assert create_response.status_code == 200
            payload = create_response.json()
            assert payload['run_id']
            assert payload['status'] == 'awaiting_approval'
            assert payload['report'] == ''
            assert payload['evidence'] == []
            assert payload['plan'] is not None
            assert len(payload['plan']['search_queries']) >= 1
            assert payload['planned_stages'] == [
                "intake", "plan", "retrieve", "tool-exec", "synthesize", "review", "persist",
            ]


def test_approve_resumes_and_returns_final_report(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with (
        patch("fin_agent.adapters.search.exa.client.Exa") as mock_exa_cls,
        patch.object(OpenAIClient, "chat", AsyncMock(side_effect=_mock_llm_chat_with_tickers)),
        patch(
            "fin_agent.adapters.market_data.yfinance.client.YFinanceClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
        patch(
            "fin_agent.adapters.market_data.akshare.client.AKShareClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
    ):
        _mock_llm_chat_with_tickers._count = 0
        mock_exa_cls.return_value.search.return_value = type(
            "R", (), {"results": []}
        )()

        with TestClient(create_default_app()) as client:
            plan_response = client.post(
                '/v1/research/runs',
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL', 'mode': 'plan'},
            )
            assert plan_response.status_code == 200
            plan_payload = plan_response.json()
            assert plan_payload['status'] == 'awaiting_approval'
            run_id = plan_payload['run_id']

            approve_response = client.post(
                f'/v1/research/runs/{run_id}/approve',
                json={},
            )
            assert approve_response.status_code == 200
            final_payload = approve_response.json()
            assert final_payload['run_id'] == run_id
            assert final_payload['status'] in ('completed', 'failed')
            assert final_payload['report'] != ''
            assert len(final_payload['evidence']) > 0

            stage_names = {t['stage'] for t in final_payload['trace']}
            assert {'intake', 'plan'} <= stage_names
            assert {'retrieve', 'tool-exec', 'synthesize', 'persist'} <= stage_names


def test_approve_with_edited_plan_uses_edited_plan(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')
    monkeypatch.setenv('FIN_AGENT__PROVIDERS__DEFAULT_SELECTION__SEARCH', 'exa')

    captured_queries: list[str] = []

    with (
        patch("fin_agent.adapters.search.exa.client.Exa") as mock_exa_cls,
        patch.object(OpenAIClient, "chat", AsyncMock(side_effect=_mock_llm_chat)),
        patch(
            "fin_agent.adapters.search.exa.client.ExaSearchClient.search",
            autospec=True,
            side_effect=_make_search_spy(captured_queries),
        ),
        patch(
            "fin_agent.adapters.market_data.yfinance.client.YFinanceClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
        patch(
            "fin_agent.adapters.market_data.akshare.client.AKShareClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
    ):
        _mock_llm_chat._count = 0
        mock_exa_cls.return_value.search.return_value = type(
            "R", (), {"results": []}
        )()

        with TestClient(create_default_app()) as client:
            plan_response = client.post(
                '/v1/research/runs',
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL', 'mode': 'plan'},
            )
            assert plan_response.status_code == 200
            plan_payload = plan_response.json()
            run_id = plan_payload['run_id']
            original_queries = [q['query'] for q in plan_payload['plan']['search_queries']]
            assert "MY EDITED QUERY" not in original_queries

            edited_plan = {
                "search_queries": [{"query": "MY EDITED QUERY", "max_results": 1}],
                "market_data": [],
                "financials": [],
                "fetch_company_info_tickers": [],
                "fetch_analyst_data_tickers": [],
                "fetch_crypto_tickers": [],
            }
            approve_response = client.post(
                f'/v1/research/runs/{run_id}/approve',
                json={"plan": edited_plan},
            )
            assert approve_response.status_code == 200
            final_payload = approve_response.json()
            assert final_payload['status'] in ('completed', 'failed')
            assert final_payload['plan']['search_queries'][0]['query'] == "MY EDITED QUERY"

            assert captured_queries == ["MY EDITED QUERY"]


def test_approve_unknown_run_id_returns_404(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            response = client.post(
                '/v1/research/runs/no-such-run-id/approve',
                json={},
            )
            assert response.status_code == 404


def test_approve_run_not_awaiting_approval_returns_404(monkeypatch) -> None:
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
            run_id = create_response.json()['run_id']
            assert create_response.json()['status'] in ('completed', 'failed')

            approve_response = client.post(
                f'/v1/research/runs/{run_id}/approve',
                json={},
            )
            assert approve_response.status_code == 404


def test_auto_mode_unchanged_default(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with (
        patch("fin_agent.adapters.search.exa.client.Exa") as mock_exa_cls,
        patch.object(OpenAIClient, "chat", AsyncMock(side_effect=_mock_llm_chat)),
        patch(
            "fin_agent.adapters.market_data.yfinance.client.YFinanceClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
        patch(
            "fin_agent.adapters.market_data.akshare.client.AKShareClient.get_market_data",
            side_effect=_mock_market_data_get,
        ),
    ):
        _mock_llm_chat._count = 0
        mock_exa_cls.return_value.search.return_value = type(
            "R", (), {"results": []}
        )()

        with TestClient(create_default_app()) as client:
            create_response = client.post(
                '/v1/research/runs',
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL', 'mode': 'auto'},
            )
            assert create_response.status_code == 200
            payload = create_response.json()
            assert payload['run_id']
            assert payload['status'] in ('completed', 'failed')
            assert payload['planned_stages'] == [
                "intake", "plan", "retrieve", "tool-exec", "synthesize", "review", "persist",
            ]
            assert payload['report'] != ''
            assert payload['plan'] is None

            _mock_llm_chat._count = 0
            no_mode_response = client.post(
                '/v1/research/runs',
                json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL'},
            )
            assert no_mode_response.status_code == 200
            no_mode_payload = no_mode_response.json()
            assert no_mode_payload['status'] in ('completed', 'failed')
            assert no_mode_payload['planned_stages'] == payload['planned_stages']
            assert no_mode_payload['report'] != ''
            assert no_mode_payload['plan'] is None


class _FakeUrlResponse:
    """Offline stand-in for urlopen's context manager in the install test."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int = -1) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _skill_env(monkeypatch, tmp_path) -> None:
    """Common env for the skill-management endpoints: keys + an isolated pool."""
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')
    monkeypatch.setenv('FIN_AGENT__RUNTIME__DATA_DIR', str(tmp_path))


def test_skill_upload_appears_in_details_then_delete(monkeypatch, tmp_path) -> None:
    _skill_env(monkeypatch, tmp_path)
    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            md = (
                "---\nname: my-custom\ndescription: My custom skill\n"
                "aliases: [mc]\n---\nCustom secret body."
            )
            up = client.post(
                '/v1/skills/upload',
                files={'file': ('SKILL.md', md, 'text/markdown')},
            )
            assert up.status_code == 200
            body = up.json()
            assert body['name'] == 'my-custom'
            assert body['source'] == 'external'
            assert body['overwritten'] is False
            assert body['total_skills'] >= 3

            details_resp = client.get('/v1/skills/details')
            details = details_resp.json()['skills']
            entry = next(s for s in details if s['name'] == 'my-custom')
            assert entry['source'] == 'external'
            assert entry['trigger'] == '/my-custom'
            assert 'mc' in entry['aliases']
            # The manifest body must never leak into the management listing.
            assert 'Custom secret body' not in details_resp.text

            # Hot-reload makes it usable in the anonymous picker with no restart.
            picker = [s['name'] for s in client.get('/v1/skills').json()['skills']]
            assert 'my-custom' in picker

            deleted = client.delete('/v1/skills/my-custom')
            assert deleted.status_code == 200
            assert deleted.json()['name'] == 'my-custom'

            after = [s['name'] for s in client.get('/v1/skills/details').json()['skills']]
            assert 'my-custom' not in after


def test_delete_builtin_skill_is_forbidden(monkeypatch, tmp_path) -> None:
    _skill_env(monkeypatch, tmp_path)
    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            # Shipped builtin (has a SKILL.md on disk) -> 403.
            assert client.delete('/v1/skills/valuation').status_code == 403
            # Structural builtin (no file, source='builtin') -> 403.
            assert client.delete('/v1/skills/research').status_code == 403
            # Unknown name -> 404.
            assert client.delete('/v1/skills/does-not-exist').status_code == 404


def test_install_skill_from_url_endpoint(monkeypatch, tmp_path) -> None:
    _skill_env(monkeypatch, tmp_path)
    md = "---\nname: url-skill\ndescription: From URL\n---\nURL body."
    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
        patch("urllib.request.urlopen", return_value=_FakeUrlResponse(md.encode("utf-8"))),
    ):
        with TestClient(create_default_app()) as client:
            ok = client.post(
                '/v1/skills/install',
                json={'url': 'https://example.com/skills/url-skill/SKILL.md'},
            )
            assert ok.status_code == 200
            assert ok.json()['name'] == 'url-skill'
            names = [s['name'] for s in client.get('/v1/skills/details').json()['skills']]
            assert 'url-skill' in names

            # A non-http(s) scheme is rejected at the boundary with 400.
            bad = client.post('/v1/skills/install', json={'url': 'file:///etc/passwd'})
            assert bad.status_code == 400


def test_upload_empty_file_is_rejected(monkeypatch, tmp_path) -> None:
    _skill_env(monkeypatch, tmp_path)
    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            r = client.post(
                '/v1/skills/upload',
                files={'file': ('SKILL.md', '', 'text/markdown')},
            )
            assert r.status_code == 400


def test_reload_endpoint_picks_up_handdropped_skill(monkeypatch, tmp_path) -> None:
    _skill_env(monkeypatch, tmp_path)
    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            # Drop a skill straight onto disk, bypassing the install/upload API.
            skill_dir = tmp_path / "skills" / "dropped"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: dropped\n---\nDropped body.", encoding="utf-8"
            )
            before = [s['name'] for s in client.get('/v1/skills').json()['skills']]
            assert 'dropped' not in before

            assert client.post('/v1/skills/reload').status_code == 200

            after = [s['name'] for s in client.get('/v1/skills').json()['skills']]
            assert 'dropped' in after


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
