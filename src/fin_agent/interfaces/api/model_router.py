"""Authenticated BYOK settings and explicit personal-model research routes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError

from fin_agent.domain.types import ResearchRequest
from fin_agent.interfaces.api.auth_router import _get_current_user
from fin_agent.interfaces.api.router import research_events
from fin_agent.services.model_connections import (
    ConnectionInput,
    ModelConnections,
    PersonalModelConfig,
)


async def read_connection(request: Request, connections: ModelConnections) -> PersonalModelConfig:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 16384:
            raise HTTPException(413, "Connection settings are too large.")
    try:
        payload = ConnectionInput.model_validate(json.loads(data))
        return connections.configure(payload)
    except ValueError:
        # FastAPI's default validation response includes input values, including raw keys.
        raise HTTPException(
            400,
            "设置无效：检查密钥、模型及已允许的 HTTPS 基础地址。 / Invalid connection settings.",
        ) from None


def build_model_router() -> APIRouter:
    router = APIRouter(tags=["model-settings"])

    @router.get("/v1/user/model-connection/options")
    async def options(request: Request, response: Response) -> dict[str, list[str]]:
        response.headers["Cache-Control"] = "no-store"
        return {"allowed_hosts": request.app.state.container.model_connections.allowed_hosts}

    @router.get("/v1/user/model-connection")
    async def get_connection(
        request: Request, response: Response
    ) -> dict[str, dict[str, str] | None]:
        user = _get_current_user(request)
        response.headers["Cache-Control"] = "no-store"
        connection = request.app.state.container.model_connections.get(user.id)
        return {"connection": connection.metadata() if connection else None}

    @router.put("/v1/user/model-connection")
    async def save_connection(request: Request, response: Response) -> dict[str, dict[str, str]]:
        user = _get_current_user(request)
        connections = request.app.state.container.model_connections
        config = await read_connection(request, connections)
        try:
            connection = connections.save(user.id, config)
        except ValueError:
            raise HTTPException(429, "连接数量已达上限，请稍后再试。 / Capacity reached.") from None
        response.headers["Cache-Control"] = "no-store"
        return {"connection": connection.metadata()}

    @router.delete("/v1/user/model-connection", status_code=204)
    async def disconnect(request: Request) -> None:
        user = _get_current_user(request)
        request.app.state.container.model_connections.remove(user.id)

    @router.post("/v1/user/model-connection/test")
    async def test_connection(request: Request, response: Response) -> dict[str, bool]:
        user = _get_current_user(request)
        connections = request.app.state.container.model_connections
        connection = connections.get(user.id)
        if connection is None:
            raise HTTPException(409, "请先保存连接；过期后需重新填写。 / Save a connection first.")
        try:
            async with connections.client(connection.config) as client:
                await client.check_connection()
        except (APITimeoutError, httpx.TimeoutException):
            raise HTTPException(504, "连接超时，未自动重试。 / Connection timed out.") from None
        except (APIConnectionError, httpx.RequestError):
            raise HTTPException(502, "无法连接模型服务。 / Cannot reach model service.") from None
        except (APIStatusError, httpx.HTTPStatusError) as exc:
            detail = {
                401: "密钥无效或已失效 / Invalid API key",
                403: "密钥无此模型权限 / Model access denied",
                429: "额度不足或请求受限 / Quota or rate limit",
            }.get(
                exc.response.status_code, "接口、模型或参数不兼容 / Incompatible endpoint or model"
            )
            raise HTTPException(502, detail) from None
        except Exception:
            raise HTTPException(502, "模型响应无效。 / Invalid model response.") from None
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True}

    @router.post("/v1/research/personal/stream")
    async def personal_research(payload: ResearchRequest, request: Request) -> StreamingResponse:
        if payload.mode == "plan":
            raise HTTPException(
                409,
                "计划审批暂不支持个人 API，请使用自动模式。 / "
                "Personal API supports auto mode only.",
            )
        user = _get_current_user(request)
        container = request.app.state.container
        connection = container.model_connections.get(user.id)
        if connection is None:
            raise HTTPException(
                409,
                "个人 API 未连接或已过期；不会切换为系统密钥。 / Personal API unavailable.",
            )

        async def events() -> AsyncIterator[str]:
            async with container.model_connections.client(connection.config) as llm:
                service = container.research_service.with_llm(
                    llm,
                    model=connection.config.model,
                    protocol=connection.config.protocol,
                    owner_user_id=user.id,
                )
                async for event in research_events(payload, service):
                    yield event

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
