"""Owner-only local Codex access, unavailable in commercial deployments."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from ipaddress import ip_address
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from fin_agent.adapters.llm.codex import CodexError, LocalCodex
from fin_agent.domain.types import LLMMessage, ResearchRequest
from fin_agent.interfaces.api.auth_router import _get_current_user
from fin_agent.interfaces.api.router import research_events


def local_owner(request: Request) -> tuple[LocalCodex, str]:
    user = _get_current_user(request)
    container = request.app.state.container
    settings = container.settings
    try:
        loopback = bool(request.client and ip_address(request.client.host).is_loopback)
    except ValueError:
        loopback = False
    origin = request.headers.get("origin")
    same_origin = origin is None or origin.rstrip("/") == str(request.base_url).rstrip("/")
    if (
        settings.runtime.commercial_mode
        or not settings.codex.enabled
        or user.id != settings.codex.owner_user_id
        or not loopback
        or not same_origin
        or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or request.headers.get("x-forwarded-for")
        or request.headers.get("forwarded")
    ):
        raise HTTPException(403, "仅指定账户可在本机使用 Codex。 / Local owner access only.")
    return container.local_codex, user.id


def build_codex_router() -> APIRouter:
    router = APIRouter(tags=["local-codex"])

    @router.get("/v1/user/model-access")
    async def model_access(request: Request, response: Response) -> dict[str, bool]:
        settings = request.app.state.container.settings
        try:
            local_owner(request)
            available = True
        except HTTPException:
            available = False
        response.headers["Cache-Control"] = "no-store"
        return {
            "local_codex": available,
            "system_model": (
                settings.runtime.allow_system_model and not settings.runtime.commercial_mode
            ),
            "commercial_mode": settings.runtime.commercial_mode,
        }

    @router.get("/v1/user/codex")
    async def codex_status(request: Request, response: Response) -> dict[str, Any]:
        bridge, _ = local_owner(request)
        try:
            async with bridge.client() as client:
                response.headers["Cache-Control"] = "no-store"
                return {"ready": True, "model": client.model, "auth": "chatgpt"}
        except CodexError as exc:
            raise HTTPException(503, str(exc)) from None

    @router.post("/v1/user/codex/test")
    async def test_codex(request: Request, response: Response) -> dict[str, Any]:
        bridge, _ = local_owner(request)
        try:
            async with bridge.client() as client:
                answer = await client.chat([LLMMessage(role="user", content="Reply only OK.")])
                response.headers["Cache-Control"] = "no-store"
                return {
                    "ok": True,
                    "model": answer.model,
                    "text": answer.message.content,
                    "input_tokens": answer.usage_prompt_tokens,
                    "output_tokens": answer.usage_completion_tokens,
                }
        except CodexError as exc:
            raise HTTPException(502, str(exc)) from None

    @router.post("/v1/research/codex/stream")
    async def codex_research(payload: ResearchRequest, request: Request) -> StreamingResponse:
        bridge, user_id = local_owner(request)
        if bridge.busy:
            raise HTTPException(429, "本机 Codex 忙，请勿重复提交。 / Local Codex is busy.")

        async def events() -> AsyncIterator[str]:
            try:
                async with bridge.client() as llm:
                    service = request.app.state.container.research_service.with_llm(
                        llm,
                        model=llm.model,
                        protocol="codex",
                        owner_user_id=user_id,
                        source="local_codex",
                    )
                    async for event in research_events(payload, service):
                        yield event
            except CodexError as exc:
                yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
