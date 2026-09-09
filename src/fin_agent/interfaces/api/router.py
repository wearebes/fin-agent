"""HTTP routes for the fin-agent API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fin_agent.domain.types import (
    JsonDict,
    ResearchRequest,
    RetrievalPlan,
    RunResult,
    TraceResponse,
)
from fin_agent.interfaces.api.auth_router import _get_current_user
from fin_agent.services import skill_installer
from fin_agent.services.research import ResearchService
from fin_agent.skills.loader import BUILTIN_SKILLS_DIR

logger = logging.getLogger(__name__)


def require_system_model(request: Request) -> None:
    settings = getattr(request.app.state.container, "settings", None)
    if settings is None:
        return
    if settings.runtime.commercial_mode or not settings.runtime.allow_system_model:
        raise HTTPException(403, "系统共享模型已关闭，请登录并连接自己的 API。 / Use your own API.")


def require_run_access(request: Request, result: RunResult) -> None:
    owner = result.providers.get("owner_user_id")
    if owner:
        if _get_current_user(request).id != owner:
            raise HTTPException(404, "Run not found.")
        return
    settings = getattr(request.app.state.container, "settings", None)
    if settings is not None and settings.runtime.commercial_mode:
        raise HTTPException(404, "Run not found.")


async def research_events(payload: ResearchRequest, service: ResearchService) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def execute() -> None:
        try:

            def on_progress(event: BaseModel) -> None:
                queue.put_nowait(("progress", event.model_dump_json()))

            result = (
                await service.run_plan(payload, on_progress=on_progress)
                if payload.mode == "plan"
                else await service.run(payload, on_progress=on_progress)
            )
            queue.put_nowait(("result", result.model_dump_json()))
        except Exception:
            logger.exception("Streaming research failed")
            queue.put_nowait(("error", '{"message":"Research could not be completed."}'))

    task = asyncio.create_task(execute())
    try:
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"event: {event}\ndata: {data}\n\n"
            if event in {"result", "error"}:
                break
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class ApproveRunRequest(BaseModel):
    """Body for POST /v1/research/runs/{run_id}/approve.

    `plan=None` (the default — an empty `{}` body is valid) means "approve
    the plan as originally generated"; a populated `plan` wholesale-replaces
    `ResearchContext.plan` before the remaining stages resume (see
    `ResearchService.approve`)."""

    plan: RetrievalPlan | None = None


class SkillDescriptor(BaseModel):
    """Catalog view of a skill. No executable reference is ever exposed."""

    name: str
    trigger: str
    aliases: list[str]
    description: str
    input_schema: JsonDict


class SkillsResponse(BaseModel):
    skills: list[SkillDescriptor]


class SkillDetail(BaseModel):
    """Management view of a skill: catalog fields plus provenance.

    Adds ``source`` (and ``version``) over :class:`SkillDescriptor` so the
    admin UI can tell a locked builtin from a removable external skill. Like
    the descriptor, it still never carries the manifest ``body`` or ``path`` —
    nothing injectable crosses this boundary.
    """

    name: str
    trigger: str
    aliases: list[str]
    description: str
    input_schema: JsonDict
    source: str
    version: str


class SkillDetailsResponse(BaseModel):
    skills: list[SkillDetail]


class InstallSkillRequest(BaseModel):
    url: str


class SkillMutationResult(BaseModel):
    """Common result for install/upload/delete/reload: always reports the new
    total so the client can reconcile its list; install/upload also echo what
    landed."""

    total_skills: int
    name: str | None = None
    source: str | None = None
    overwritten: bool | None = None


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/v1/skills", response_model=SkillsResponse, tags=["skills"])
    def list_skills(request: Request) -> SkillsResponse:
        registry = request.app.state.container.skill_registry
        return SkillsResponse(
            skills=[
                SkillDescriptor(
                    name=s.name,
                    trigger=s.trigger.slash,
                    aliases=s.trigger.aliases,
                    description=s.description,
                    input_schema=s.input_schema,
                )
                for s in registry.list()
            ]
        )

    @router.get("/v1/skills/details", response_model=SkillDetailsResponse, tags=["skills"])
    def list_skill_details(request: Request) -> SkillDetailsResponse:
        """Catalog listing for the admin UI: same fields as ``/v1/skills`` plus
        ``source``/``version``, read from the full catalog so builtin and
        external skills are distinguishable. Body text still never crosses."""
        catalog = request.app.state.container.skill_catalog
        return SkillDetailsResponse(
            skills=[
                SkillDetail(
                    name=m.name,
                    trigger=f"/{m.name}",
                    aliases=m.aliases,
                    description=m.description,
                    input_schema=m.input_schema,
                    source=m.source,
                    version=m.version,
                )
                for m in catalog.list()
            ]
        )

    @router.post("/v1/skills/install", response_model=SkillMutationResult, tags=["skills"])
    def install_skill(payload: InstallSkillRequest, request: Request) -> SkillMutationResult:
        """Install a skill by downloading its SKILL.md from a URL, then
        hot-reload so it is immediately resolvable without a restart."""
        container = request.app.state.container
        try:
            installed = skill_installer.install_from_url(payload.url, container.external_skills_dir)
        except skill_installer.SkillInstallError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        total = container.reload_skills()
        return SkillMutationResult(
            name=installed.name,
            source="external",
            overwritten=installed.overwritten,
            total_skills=total,
        )

    @router.post("/v1/skills/upload", response_model=SkillMutationResult, tags=["skills"])
    async def upload_skill(
        request: Request, file: Annotated[UploadFile, File()]
    ) -> SkillMutationResult:
        """Install a skill from an uploaded SKILL.md, then hot-reload it."""
        container = request.app.state.container
        raw = await file.read()
        limit_kb = skill_installer.MAX_SKILL_BYTES // 1024
        if len(raw) > skill_installer.MAX_SKILL_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded skill exceeds the {limit_kb} KB limit.",
            )
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded skill is not valid UTF-8 text.",
            ) from exc
        name_hint = Path(file.filename or "").stem or None
        try:
            installed = skill_installer.install_from_content(
                content, name_hint, container.external_skills_dir
            )
        except skill_installer.SkillInstallError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        total = container.reload_skills()
        return SkillMutationResult(
            name=installed.name,
            source="external",
            overwritten=installed.overwritten,
            total_skills=total,
        )

    @router.delete("/v1/skills/{name}", response_model=SkillMutationResult, tags=["skills"])
    def delete_skill(name: str, request: Request) -> SkillMutationResult:
        """Remove an external skill. Builtins (structural or shipped) are
        rejected with 403; an unknown name is 404."""
        container = request.app.state.container
        manifest = container.skill_catalog.get(name)
        if manifest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{name}' was not found.",
            )
        if manifest.source != "external":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Skill '{name}' is a builtin and cannot be removed.",
            )
        try:
            skill_installer.uninstall(name, container.external_skills_dir, BUILTIN_SKILLS_DIR)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except skill_installer.SkillInstallError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        total = container.reload_skills()
        return SkillMutationResult(name=name, total_skills=total)

    @router.post("/v1/skills/reload", response_model=SkillMutationResult, tags=["skills"])
    def reload_skills(request: Request) -> SkillMutationResult:
        """Re-scan the skill dirs without a restart — for the case where files
        were dropped into the external pool directly, bypassing install/upload."""
        total = request.app.state.container.reload_skills()
        return SkillMutationResult(total_skills=total)

    @router.post("/v1/research/stream", tags=["research"])
    async def stream_research(payload: ResearchRequest, request: Request) -> StreamingResponse:
        require_system_model(request)
        return StreamingResponse(
            research_events(payload, request.app.state.container.research_service),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/v1/research/runs", response_model=RunResult, tags=["research"])
    async def create_research_run(payload: ResearchRequest, request: Request) -> RunResult:
        require_system_model(request)
        service = request.app.state.container.research_service
        if payload.mode == "plan":
            return await service.run_plan(payload)
        result: RunResult = await service.run(payload)
        return result

    @router.post(
        "/v1/research/runs/{run_id}/approve",
        response_model=RunResult,
        tags=["research"],
    )
    async def approve_research_run(
        run_id: str, payload: ApproveRunRequest, request: Request
    ) -> RunResult:
        require_system_model(request)
        pending = request.app.state.container.research_service.get_run(run_id)
        if pending is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
        require_run_access(request, pending)
        result: RunResult | None = await request.app.state.container.research_service.approve(
            run_id, payload.plan
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pending plan found for run '{run_id}'.",
            )
        require_run_access(request, result)
        return result

    @router.get("/v1/research/runs/{run_id}", response_model=RunResult, tags=["research"])
    def get_research_run(run_id: str, request: Request) -> RunResult:
        result: RunResult | None = request.app.state.container.research_service.get_run(run_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' was not found.",
            )
        require_run_access(request, result)
        return result

    @router.get(
        "/v1/research/runs/{run_id}/trace",
        response_model=TraceResponse,
        tags=["research"],
    )
    def get_research_trace(run_id: str, request: Request) -> TraceResponse:
        service = request.app.state.container.research_service
        result = service.get_run(run_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
        require_run_access(request, result)
        trace = service.get_trace(run_id)
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace for run '{run_id}' was not found.",
            )
        return TraceResponse(run_id=run_id, trace=trace)

    return router
