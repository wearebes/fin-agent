from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fin_agent.bootstrap.app import create_default_app
from fin_agent.bootstrap.cli import app as cli_app
from fin_agent.bootstrap.settings import export_env_example, load_settings


def _set_required_provider_env(monkeypatch) -> None:
    monkeypatch.setenv("FIN_AGENT__OPENAI__API_KEY", "sk-test")
    monkeypatch.setenv("FIN_AGENT__SEARCH__API_KEY", "search-test")


def test_load_settings_merges_layered_yaml_and_env(monkeypatch) -> None:
    _set_required_provider_env(monkeypatch)
    monkeypatch.setenv("FIN_AGENT__LOGGING__LEVEL", "ERROR")

    settings = load_settings("test")

    assert settings.app.environment.value == "test"
    assert settings.database.url == "sqlite:///./var/fin_agent-test.db"
    assert settings.logging.level == "ERROR"
    assert settings.openai.api_key is not None
    assert settings.source_files[0].name == "base.yaml"
    assert settings.source_files[1].name == "test.yaml"


def test_export_env_example_matches_repository_file() -> None:
    env_example_path = Path(".env.example")
    assert export_env_example() == env_example_path.read_text(encoding="utf-8")


def test_config_modules_import_without_bootstrap() -> None:
    from fin_agent.adapters.llm.openai.config import OpenAIConfig
    from fin_agent.adapters.market_data.yfinance.config import YFinanceConfig
    from fin_agent.adapters.search.exa.config import ExaSearchConfig
    from fin_agent.workflows.research.config import ResearchWorkflowConfig

    assert OpenAIConfig().model == "gpt-4.1-mini"
    assert YFinanceConfig().history_period == "1y"
    assert ExaSearchConfig().max_results == 8
    assert ResearchWorkflowConfig().max_tool_calls == 3


def test_api_and_cli_read_the_same_settings(monkeypatch) -> None:
    _set_required_provider_env(monkeypatch)
    monkeypatch.setenv("FIN_AGENT__APP__ENVIRONMENT", "test")

    app = create_default_app()
    with TestClient(app) as client:
        app_settings = client.app.state.settings
        response = client.get("/healthz")
        assert response.status_code == 200

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 0
    doctor_report = json.loads(result.stdout)
    assert doctor_report["environment"] == app_settings.app.environment.value
    assert (
        doctor_report["providers"]
        == app_settings.providers.default_selection.model_dump(mode="json")
    )
