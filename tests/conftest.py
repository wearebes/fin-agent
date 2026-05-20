from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def clear_fin_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FIN_AGENT__"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "fin-agent-test")
    monkeypatch.setenv("CONDA_PREFIX", os.getcwd())
