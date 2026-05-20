from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fin_agent.bootstrap.app import create_default_app
from fin_agent.bootstrap.cli import app as cli_app


def test_research_run_round_trip(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    with TestClient(create_default_app()) as client:
        create_response = client.post(
            '/v1/research/runs',
            json={'question': 'Summarize AAPL momentum', 'ticker': 'AAPL'},
        )
        assert create_response.status_code == 200
        payload = create_response.json()
        assert payload['environment'] == 'local'
        assert payload['evidence'][0]['source'] == 'scaffold'
        assert 'Scaffold only' in payload['evidence'][0]['summary']
        assert 'No external retrieval' in payload['trace'][1]['detail']

        trace_response = client.get(f"/v1/research/runs/{payload['run_id']}/trace")
        assert trace_response.status_code == 200
        assert trace_response.json()['run_id'] == payload['run_id']


def test_research_cli_reports_scaffold_semantics(monkeypatch) -> None:
    monkeypatch.setenv('FIN_AGENT__OPENAI__API_KEY', 'sk-test')
    monkeypatch.setenv('FIN_AGENT__SEARCH__API_KEY', 'search-test')

    result = CliRunner().invoke(
        cli_app,
        ['research', 'run', '--question', 'Summarize AAPL momentum', '--ticker', 'AAPL'],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload['evidence'][0]['source'] == 'scaffold'
    assert 'Scaffold only' in payload['evidence'][0]['summary']
    assert 'No external retrieval' in payload['trace'][1]['detail']
