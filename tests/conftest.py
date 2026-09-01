from __future__ import annotations

import os
import socket

import pytest


@pytest.fixture(autouse=True)
def clear_fin_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from fin_agent.bootstrap.settings import AppSettings

    # Tests must never read the developer's real credentials or database URL.
    monkeypatch.setitem(AppSettings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("FIN_AGENT__"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "fin-agent-test")
    monkeypatch.setenv("CONDA_PREFIX", os.getcwd())


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail on accidental live calls, including yfinance's native curl transport."""
    import httpx
    import requests
    from curl_cffi import requests as curl_requests

    def blocked(*args, **kwargs):
        pytest.fail("External network is disabled in tests; inject a stub provider.")

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        blocked()

    def local_only_ex(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect_ex(sock, address)
        blocked()

    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setattr(socket.socket, "connect_ex", local_only_ex)
    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(curl_requests.Session, "request", blocked)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", blocked)
    # ASGI TestClient uses its own transport and remains usable without sockets.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
