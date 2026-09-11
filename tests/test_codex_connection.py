"""Offline protocol and access-control tests; live evidence is recorded separately."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fin_agent.adapters.llm.codex import (
    CodexConfig,
    CodexError,
    CodexSession,
    CodexTimeoutError,
    LocalCodex,
)
from fin_agent.bootstrap.app import create_app
from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.domain.types import LLMMessage, LLMResponse
from fin_agent.interfaces.api.codex_router import build_codex_router
from fin_agent.interfaces.api.router import build_router


@pytest.mark.asyncio
async def test_start_disables_tools_and_only_inherits_configured_windows_proxy(monkeypatch):
    from fin_agent.adapters.llm import codex

    for key in list(codex.os.environ):
        if key.lower() in {"https_proxy", "all_proxy"}:
            monkeypatch.delenv(key)
    monkeypatch.setattr(codex, "getproxies", lambda: {"https": "http://127.0.0.1:10809"})
    monkeypatch.setattr(codex.shutil, "which", lambda _: "codex")
    process = SimpleNamespace(returncode=0)
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", spawn)
    session = CodexSession(CodexConfig())
    session.send = AsyncMock()
    session.rpc = AsyncMock(
        side_effect=[
            {},
            {"account": {"type": "chatgpt"}},
            {
                "config": {"mcp_servers": {"private-files": {}}, "model": "offline-model"},
            },
        ]
    )
    try:
        await session.start()
        arguments = spawn.call_args.args
        assert "features.shell_tool=false" in arguments
        assert "features.apps=false" in arguments
        assert "features.plugins=false" in arguments
        assert session._overrides["mcp_servers"]["private-files"]["enabled"] is False
        profile = session._overrides["permissions"]["finagent-text"]
        assert profile["filesystem"][":root"] == "deny"
        assert profile["network"]["enabled"] is False
        if codex.os.name == "nt":
            assert spawn.call_args.kwargs["env"]["HTTPS_PROXY"] == "http://127.0.0.1:10809"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_timeout_closes_local_process_without_retry(tmp_path):
    session = CodexSession(CodexConfig())
    session.config.timeout_seconds = 0.01
    session._directory = SimpleNamespace(name=str(tmp_path))
    session.close = AsyncMock()

    async def never_completes(*_):
        await asyncio.Event().wait()

    session._chat = AsyncMock(side_effect=never_completes)
    with pytest.raises(CodexTimeoutError, match="timed out"):
        await session.chat([LLMMessage(role="user", content="q")])
    session._chat.assert_awaited_once()
    session.close.assert_awaited_once()


def session_with_lines(*messages):
    session = CodexSession(CodexConfig())
    reader = asyncio.StreamReader()
    for message in messages:
        reader.feed_data((json.dumps(message) + "\n").encode())
    reader.feed_eof()
    session.process = SimpleNamespace(stdout=reader)
    return session


@pytest.mark.asyncio
async def test_rpc_preserves_events_arriving_before_response():
    notification = {"method": "thread/started", "params": {"threadId": "one"}}
    session = session_with_lines(notification, {"id": 1, "result": {"accepted": True}})
    session.send = AsyncMock()
    assert await session.rpc("thread/start", {}) == {"accepted": True}
    assert session._events.popleft() == notification
    session.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        {"id": 9, "method": "item/commandExecution/requestApproval", "params": {}},
        {"method": "item/started", "params": {"item": {"type": "commandExecution"}}},
        {"method": "item/started", "params": {"item": {"type": "mcpToolCall"}}},
        {"method": "item/started", "params": {"item": {"type": "imageView"}}},
        ["invalid-response"],
    ],
)
async def test_non_text_operations_and_invalid_responses_fail_closed(message):
    with pytest.raises(CodexError):
        await session_with_lines(message).read()


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_raw_private_data():
    session = session_with_lines({"id": 1, "error": {"message": "private-provider-secret"}})
    session.send = AsyncMock()
    with pytest.raises(CodexError) as error:
        await session.rpc("turn/start", {})
    assert "private-provider-secret" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,text", [("completed", "中文报告"), ("completed", ""), ("failed", "partial")]
)
async def test_chat_requires_completed_turn_and_real_text(tmp_path, status, text):
    session = CodexSession(CodexConfig())
    session._directory = SimpleNamespace(name=str(tmp_path))
    session.rpc = AsyncMock(
        side_effect=[
            {
                "thread": {"id": "one"},
                "model": "offline-model",
                "activePermissionProfile": {"id": "finagent-text"},
            },
            {"turn": {"id": "turn"}},
        ]
    )
    session.read = AsyncMock(
        side_effect=[
            {
                "method": "item/completed",
                "params": {
                    "threadId": "one",
                    "item": {
                        "type": "agentMessage",
                        "phase": "commentary",
                        "text": "I will analyze this.",
                    },
                },
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "one",
                    "tokenUsage": {"last": {"inputTokens": 12, "outputTokens": 3}},
                },
            },
            {
                "method": "item/completed",
                "params": {"threadId": "one", "item": {"type": "agentMessage", "text": text}},
            },
            {"method": "turn/completed", "params": {"threadId": "one", "turn": {"status": status}}},
        ]
    )
    messages = [LLMMessage(role="user", content="offline input")]
    if status != "completed" or not text:
        with pytest.raises(CodexError):
            await session.chat(messages)
        return
    response = await session.chat(messages, max_tokens=16384)
    assert response.message.content == text
    assert response.usage_completion_tokens == 3
    thread_params = session.rpc.call_args_list[0].args[1]
    assert thread_params["ephemeral"] is True
    assert thread_params["approvalPolicy"] == "never"
    assert "sandbox" not in thread_params  # Legacy sandbox fields override named profiles.
    prompt = session.rpc.call_args_list[1].args[1]["input"][0]["text"]
    assert "at most 4096 output tokens" in prompt
    assert "16384" not in prompt


@pytest.mark.asyncio
async def test_generation_timeout_is_not_mislabeled_as_startup_failure(monkeypatch):
    monkeypatch.setattr(CodexSession, "start", AsyncMock())
    monkeypatch.setattr(CodexSession, "close", AsyncMock())
    bridge = LocalCodex(CodexConfig())
    with pytest.raises(CodexTimeoutError, match="generation timed out"):
        async with bridge.client():
            raise CodexTimeoutError("generation timed out")
    assert not bridge.busy


@pytest.mark.asyncio
async def test_missing_permission_profile_stops_before_model_call(tmp_path):
    session = CodexSession(CodexConfig())
    session._directory = SimpleNamespace(name=str(tmp_path))
    session.rpc = AsyncMock(return_value={"thread": {"id": "one"}})
    with pytest.raises(CodexError, match="Permission profile required"):
        await session.chat([LLMMessage(role="user", content="q")])
    session.rpc.assert_awaited_once()


@pytest.mark.asyncio
async def test_busy_and_cancellation_release_process(monkeypatch):
    monkeypatch.setattr(CodexSession, "start", AsyncMock())
    close = AsyncMock()
    monkeypatch.setattr(CodexSession, "close", close)
    bridge = LocalCodex(CodexConfig())
    with pytest.raises(asyncio.CancelledError):
        async with bridge.client():
            with pytest.raises(CodexError, match="busy"):
                async with bridge.client():
                    pytest.fail("Concurrent local request was admitted")
            raise asyncio.CancelledError
    assert not bridge.busy
    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_start_and_cleanup_cannot_leave_permanent_busy_lock(monkeypatch):
    monkeypatch.setattr(CodexSession, "start", AsyncMock(side_effect=CodexError("offline")))
    monkeypatch.setattr(CodexSession, "close", AsyncMock(side_effect=OSError("cleanup")))
    bridge = LocalCodex(CodexConfig())
    with pytest.raises(OSError):
        async with bridge.client():
            pytest.fail("Failed startup yielded a client")
    assert not bridge.busy


def local_app(*, commercial=False, enabled=True):
    def authenticate(token):
        if token not in {"owner", "other"}:
            raise ValueError("Invalid login")
        return SimpleNamespace(id=token)

    @asynccontextmanager
    async def provider():
        yield llm

    llm = SimpleNamespace(
        model="offline-model",
        chat=AsyncMock(
            return_value=LLMResponse(
                message=LLMMessage(role="assistant", content="offline response"),
                model="offline-model",
            )
        ),
    )
    app = FastAPI()
    app.state.container = SimpleNamespace(
        settings=SimpleNamespace(
            runtime=SimpleNamespace(commercial_mode=commercial, allow_system_model=False),
            codex=CodexConfig(enabled=enabled, owner_user_id="owner"),
        ),
        auth_service=SimpleNamespace(get_current_user=authenticate),
        local_codex=SimpleNamespace(client=provider, busy=False),
        research_service=SimpleNamespace(
            run=AsyncMock(side_effect=AssertionError("Shared key used"))
        ),
    )
    app.include_router(build_codex_router())
    app.include_router(build_router())
    return app, llm


@pytest.mark.parametrize(
    "token,peer,origin,forwarded,host,commercial,enabled",
    [
        (None, "127.0.0.1", None, None, "127.0.0.1", False, True),
        ("other", "127.0.0.1", None, None, "127.0.0.1", False, True),
        ("owner", "192.168.1.2", None, None, "127.0.0.1", False, True),
        ("owner", "127.0.0.1", "https://evil.invalid", None, "127.0.0.1", False, True),
        ("owner", "127.0.0.1", None, "203.0.113.5", "127.0.0.1", False, True),
        ("owner", "127.0.0.1", None, None, "evil.invalid", False, True),
        ("owner", "127.0.0.1", None, None, "127.0.0.1", True, True),
        ("owner", "127.0.0.1", None, None, "127.0.0.1", False, False),
    ],
)
def test_unauthorized_requests_never_reach_codex(
    token, peer, origin, forwarded, host, commercial, enabled
):
    app, llm = local_app(commercial=commercial, enabled=enabled)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if origin:
        headers["Origin"] = origin
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    with TestClient(app, base_url=f"http://{host}", client=(peer, 1234)) as client:
        assert client.get("/v1/user/model-access", headers=headers).json()["local_codex"] is False
        for method, path in [
            ("GET", "/v1/user/codex"),
            ("POST", "/v1/user/codex/test"),
            ("POST", "/v1/research/codex/stream"),
        ]:
            response = client.request(method, path, headers=headers, json={"question": "q"})
            assert response.status_code in {401, 403}
    llm.chat.assert_not_called()


def test_local_owner_status_has_no_inference_and_probe_uses_exactly_one_call():
    app, llm = local_app()
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        headers = {"Authorization": "Bearer owner", "Origin": "http://127.0.0.1"}
        assert client.get("/v1/user/codex", headers=headers).json()["ready"] is True
        llm.chat.assert_not_called()
        response = client.post("/v1/user/codex/test", headers=headers)
        assert response.json()["text"] == "offline response"
        assert response.headers["cache-control"] == "no-store"
        llm.chat.assert_awaited_once()
        for path in ["/v1/research/stream", "/v1/research/runs"]:
            assert client.post(path, json={"question": "q"}).status_code == 403
    app.state.container.research_service.run.assert_not_called()


def test_commercial_configuration_requires_persistence_secret_and_no_codex():
    settings = AppSettings(
        _env_file=None,
        runtime={"commercial_mode": True, "cors_origins": ["*"]},
        database={"backend": "memory"},
        auth={"secret_key": "short"},
        codex={"enabled": True},
        openai={"api_key": None},
    )
    errors = collect_runtime_validation_errors(settings)
    assert any("owner_user_id" in error for error in errors)
    assert any("JWT" in error for error in errors)
    assert any("SQL" in error for error in errors)
    assert any("CORS" in error for error in errors)
    assert any("must not enable" in error for error in errors)
    assert not any("OPENAI__API_KEY" in error for error in errors)


def test_commercial_app_runs_without_a_shared_api_key(tmp_path):
    settings = AppSettings(
        _env_file=None,
        runtime={"commercial_mode": True},
        database={"backend": "sql", "url": f"sqlite:///{tmp_path / 'commercial.db'}"},
        auth={"secret_key": "offline-independent-signing-secret-32"},
        openai={"api_key": None},
        proxy={"https": None},
    )
    assert collect_runtime_validation_errors(settings) == []
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/user/model-access").json() == {
            "local_codex": False,
            "system_model": False,
            "commercial_mode": True,
        }
        assert client.post("/v1/research/runs", json={"question": "q"}).status_code == 403


def test_local_launcher_persists_signing_key_and_never_claims_an_owner(tmp_path):
    from fin_agent.interfaces.local_server import local_settings

    first = local_settings(tmp_path)
    second = local_settings(tmp_path)
    assert first.auth.secret_key == second.auth.secret_key
    assert len(first.auth.secret_key.get_secret_value()) >= 32
    assert first.database.backend == "sql"
    assert not first.runtime.allow_system_model and not first.codex.enabled
    with pytest.raises(ValueError, match="Owner not found"):
        local_settings(tmp_path, "nonexistent-owner")


def test_local_launcher_binds_only_explicit_existing_username(tmp_path):
    from fin_agent.interfaces.local_server import local_settings

    settings = local_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/v1/auth/register",
            json={
                "username": "offline-owner",
                "email": "offline@example.invalid",
                "password": "offline-test-password",
            },
        )
        assert registered.status_code == 200
        user_id = registered.json()["user"]["id"]
    owner_settings = local_settings(tmp_path, "offline-owner")
    assert owner_settings.codex.enabled
    assert owner_settings.codex.owner_user_id == user_id
    assert not owner_settings.runtime.allow_system_model
    existing = local_settings(tmp_path / "desktop", "offline-owner", settings.database.url)
    assert existing.database.url == settings.database.url
    assert existing.codex.owner_user_id == user_id
