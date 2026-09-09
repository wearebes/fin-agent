"""Credential boundaries and protocol contracts, using only offline providers."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_research_workflow import PLAN_JSON, REVIEW_RESPONSE, _make_deps

from fin_agent.adapters.llm.anthropic import AnthropicClient
from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.bootstrap.app import create_app
from fin_agent.bootstrap.settings import AppSettings, RuntimeConfig
from fin_agent.domain.constants import EnvironmentName
from fin_agent.domain.types import LLMMessage, LLMResponse
from fin_agent.interfaces.api.model_router import build_model_router
from fin_agent.interfaces.api.router import build_router
from fin_agent.services.model_connections import ConnectionInput, ModelConnections
from fin_agent.services.research import ResearchService
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig

PATH = "/v1/user/model-connection"
SECRET = "offline-test-key-never-use-live"
INPUT = {"base_url": "https://api.deepseek.com", "model": "test-model", "api_key": SECRET}
HEADERS = {"Authorization": "Bearer user-a"}


def test_real_app_factory_supports_model_settings_without_provider_calls(tmp_path):
    settings = AppSettings(
        openai={"api_key": "offline-system-key"},
        proxy={"https": None},
        database={"backend": "sql", "url": f"sqlite:///{tmp_path / 'model-test.db'}"},
    )
    with TestClient(create_app(settings)) as app_client:
        assert app_client.get(PATH + "/options").status_code == 200
        registered = app_client.post(
            "/v1/auth/register",
            json={
                "username": "integration",
                "email": "integration@example.com",
                "password": "offline-test-password",
            },
        )
        assert registered.status_code == 200
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        saved = app_client.put(PATH, headers=headers, json=INPUT)
        assert saved.status_code == 200
        assert SECRET not in saved.text
        assert app_client.delete(PATH, headers=headers).status_code == 204


@pytest.fixture
def client():
    def user(token):
        if token not in {"user-a", "user-b"}:
            raise ValueError("Invalid credentials")
        return SimpleNamespace(id=token)

    app = FastAPI()
    deps = _make_deps(ResearchWorkflowConfig())
    deps.llm.chat = AsyncMock(side_effect=AssertionError("The system key must not be used"))
    app.state.container = SimpleNamespace(
        model_connections=ModelConnections(RuntimeConfig().llm_allowed_hosts),
        auth_service=SimpleNamespace(get_current_user=user),
        research_service=ResearchService(EnvironmentName.TEST, {}, InMemoryRunStore(), deps),
    )
    app.include_router(build_model_router())
    app.include_router(build_router())
    with TestClient(app) as test_client:
        yield test_client


def test_save_is_offline_and_private_and_delete_does_not_affect_other_users(client):
    saved = client.put(PATH, json=INPUT, headers=HEADERS)
    assert saved.status_code == 200
    assert saved.headers["cache-control"] == "no-store"
    assert SECRET not in saved.text and "api_key" not in saved.text
    assert client.get(PATH, headers=HEADERS).json() == saved.json()
    other = {"Authorization": "Bearer user-b"}
    assert client.get(PATH, headers=other).json() == {"connection": None}
    client.put(PATH, json={**INPUT, "model": "another-model"}, headers=other)
    assert client.delete(PATH, headers=HEADERS).status_code == 204
    assert client.get(PATH, headers=HEADERS).json() == {"connection": None}
    assert client.get(PATH, headers=other).json()["connection"]["model"] == "another-model"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", PATH),
        ("PUT", PATH),
        ("DELETE", PATH),
        ("POST", PATH + "/test"),
        ("POST", "/v1/research/personal/stream"),
    ],
)
def test_private_endpoints_require_authentication(client, method, path):
    response = client.request(method, path, json={"question": "q", **INPUT})
    assert response.status_code == 401
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://127.0.0.1",
        "https://169.254.169.254",
        "https://api.deepseek.com.evil.invalid",
        "https://user@api.deepseek.com",
        "https://api.deepseek.com:8080",
        "https://api.deepseek.com?key=secret",
        "https://api.deepseek.com#fragment",
        "https://api.deepseek.com/chat/completions",
    ],
)
def test_unsafe_endpoints_rejected_without_echoing_keys(client, url):
    response = client.put(PATH, json={**INPUT, "base_url": url}, headers=HEADERS)
    assert response.status_code == 400
    assert SECRET not in response.text


def test_validation_and_oversized_bodies_do_not_echo_secrets(client):
    for payload in [{**INPUT, "model": []}, {**INPUT, "unexpected": SECRET}]:
        response = client.put(PATH, json=payload, headers=HEADERS)
        assert response.status_code == 400
        assert SECRET not in response.text
    too_big = client.put(PATH, json={**INPUT, "api_key": "x" * 20000}, headers=HEADERS)
    assert too_big.status_code == 413
    malformed = client.put(PATH, content='{"api_key":"' + SECRET, headers=HEADERS)
    assert malformed.status_code == 400 and SECRET not in malformed.text


def test_expired_personal_connection_stops_before_any_provider_call(client):
    client.put(PATH, json=INPUT, headers=HEADERS)
    connections = client.app.state.container.model_connections
    saved = connections.get("user-a")
    connections._connections["user-a"] = replace(
        saved,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    response = client.post("/v1/research/personal/stream", json={"question": "q"}, headers=HEADERS)
    assert response.status_code == 409
    client.app.state.container.research_service._deps.llm.chat.assert_not_called()


def test_all_research_stages_use_personal_client_without_mutating_defaults(client, monkeypatch):
    personal = SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                LLMResponse(message=LLMMessage(role="assistant", content=text))
                for text in [PLAN_JSON, "```done```", "# Offline personal report"]
            ]
            + [REVIEW_RESPONSE]
        )
    )
    selected = []

    @asynccontextmanager
    async def provider(config):
        selected.append(config)
        yield personal

    monkeypatch.setattr(client.app.state.container.model_connections, "client", provider)
    client.put(PATH, json=INPUT, headers=HEADERS)
    response = client.post(
        "/v1/research/personal/stream",
        json={"question": "Analyze AAPL"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert personal.chat.await_count == 4
    assert selected[0].api_key.get_secret_value() == SECRET
    assert SECRET not in response.text and "api_key" not in response.text
    assert '"llm":"personal"' in response.text
    result = next(
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and '"run_id"' in line
    )
    run_path = f"/v1/research/runs/{result['run_id']}"
    for path in [run_path, run_path + "/trace"]:
        assert client.get(path, headers=HEADERS).status_code == 200
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer user-b"}).status_code == 404
    client.app.state.container.research_service._deps.llm.chat.assert_not_called()


def test_provider_errors_are_sanitized_and_not_retried(client, monkeypatch, caplog):
    probe = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            SECRET,
            request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
            response=httpx.Response(401),
        )
    )

    @asynccontextmanager
    async def provider(config):
        yield SimpleNamespace(check_connection=probe)

    monkeypatch.setattr(client.app.state.container.model_connections, "client", provider)
    client.put(PATH, json=INPUT, headers=HEADERS)
    response = client.post(PATH + "/test", headers=HEADERS)
    assert response.status_code == 502
    assert "Invalid API key" in response.text
    assert SECRET not in response.text and SECRET not in caplog.text
    probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_anthropic_auth_system_prompt_and_text_block_mapping():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "test-claude",
                "content": [
                    {"type": "thinking", "thinking": "private"},
                    {"type": "text", "text": "Report"},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    connections = ModelConnections(["api.anthropic.com"])
    config = connections.configure(
        ConnectionInput(
            **{**INPUT, "base_url": "https://api.anthropic.com/v1", "protocol": "anthropic"},
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        adapter = AnthropicClient(config, transport)
        answer = await adapter.chat(
            [
                LLMMessage(role="system", content="System"),
                LLMMessage(role="user", content="Question"),
            ],
            max_tokens=4096,
        )
        await adapter.check_connection()
    body = json.loads(calls[0].content)
    assert str(calls[0].url) == "https://api.anthropic.com/v1/messages"
    assert calls[0].headers["x-api-key"] == SECRET
    assert "authorization" not in calls[0].headers
    assert body["system"] == "System" and body["messages"] == [
        {"role": "user", "content": "Question"}
    ]
    assert body["max_tokens"] == 4096 and "temperature" not in body
    assert answer.message.content == "Report" and answer.usage_prompt_tokens == 10
    assert json.loads(calls[1].content)["max_tokens"] == 128


@pytest.mark.asyncio
@pytest.mark.parametrize("parameter", ["max_tokens", "max_completion_tokens"])
@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://api.deepseek.com",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://open.bigmodel.cn/api/paas/v4",
        "https://api.moonshot.cn/v1",
        "https://ark.cn-beijing.volces.com/api/v3",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    ],
)
async def test_openai_compatible_parameter_modes_and_bearer_auth(parameter, base_url):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "created": 0,
                "object": "chat.completion",
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "OK"},
                    }
                ],
            },
        )

    config = ModelConnections(RuntimeConfig().llm_allowed_hosts).configure(
        ConnectionInput(**{**INPUT, "base_url": base_url})
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        adapter = OpenAIClient(
            config,
            http_client=transport,
            max_retries=0,
            send_temperature=False,
            token_parameter=parameter,
        )
        await adapter.chat([LLMMessage(role="user", content="q")], temperature=0.2, max_tokens=4096)
        await adapter.check_connection()
        await adapter.close()
    assert calls[0].headers["authorization"] == f"Bearer {SECRET}"
    assert str(calls[0].url) == base_url + "/chat/completions"
    assert json.loads(calls[0].content)[parameter] == 4096
    assert "temperature" not in json.loads(calls[0].content)
    assert json.loads(calls[1].content)[parameter] == 128


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "", "   "])
async def test_openai_probe_rejects_empty_text_despite_http_success(content):
    response = {
        "id": "empty",
        "created": 0,
        "object": "chat.completion",
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }
    config = ModelConnections(["api.deepseek.com"]).configure(ConnectionInput(**INPUT))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as transport:
        adapter = OpenAIClient(config, http_client=transport, max_retries=0)
        with pytest.raises(ValueError, match="Invalid Chat Completions"):
            await adapter.check_connection()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", [[], [{"type": "text", "text": " "}], [{"type": "thinking", "thinking": "x"}]]
)
async def test_anthropic_probe_rejects_empty_text_despite_http_success(content):
    config = ModelConnections(["api.anthropic.com"]).configure(
        ConnectionInput(**{**INPUT, "base_url": "https://api.anthropic.com/v1"})
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"content": content}))
    ) as transport:
        adapter = AnthropicClient(config, transport)
        with pytest.raises(ValueError, match="contains no text"):
            await adapter.check_connection()
