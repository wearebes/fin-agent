"""Authenticated task submission, polling and durable history."""

from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Query, Request, Response

from fin_agent.domain.research_jobs import JobInput, ResearchJob
from fin_agent.interfaces.api.auth_router import _get_current_user
from fin_agent.interfaces.api.codex_router import local_owner
from fin_agent.interfaces.api.router import require_system_model


def job_owner(request: Request) -> str:
    if request.headers.get("authorization"):
        return _get_current_user(request).id
    require_system_model(request)
    try:
        local = request.client and ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(401, "请登录查看研究任务。 / Sign in to access research tasks.")
    if (
        request.headers.get("origin", str(request.base_url).rstrip("/")).rstrip("/")
        != str(request.base_url).rstrip("/")
        or request.headers.get("x-forwarded-for")
        or request.headers.get("forwarded")
    ):
        raise HTTPException(403, "Local access only.")
    return "local"


def build_jobs_router() -> APIRouter:
    router = APIRouter(prefix="/v1/research/jobs", tags=["research-tasks"])

    @router.post("", response_model=ResearchJob, status_code=202)
    async def submit(payload: JobInput, request: Request, response: Response):
        owner = job_owner(request)
        container = request.app.state.container
        if payload.request.mode != "auto":
            raise HTTPException(409, "后台研究请使用自动模式；计划审批仍在对话页进行。")
        if payload.source == "default":
            require_system_model(request)
        elif payload.source == "personal":
            if owner == "local" or container.model_connections.get(owner) is None:
                raise HTTPException(409, "请登录并连接自己的 API；不会切换系统模型。")
        else:
            local_owner(request)
        response.headers["Cache-Control"] = "no-store"
        try:
            return request.app.state.research_jobs.submit(payload, owner)
        except ValueError as exc:
            raise HTTPException(429, str(exc)) from None

    @router.get("")
    async def history(request: Request, response: Response, offset: int = Query(0, ge=0)):
        owner = job_owner(request)
        response.headers["Cache-Control"] = "no-store"
        jobs = request.app.state.research_jobs.store.list(owner, offset)
        return {
            "jobs": [job.model_dump(exclude={"result"}) for job in jobs],
            "next_offset": offset + len(jobs) if len(jobs) == 50 else None,
        }

    @router.get("/{job_id}", response_model=ResearchJob)
    async def detail(job_id: str, request: Request, response: Response):
        job = request.app.state.research_jobs.store.get(job_id, job_owner(request))
        if job is None:
            raise HTTPException(404, "Task not found.")
        response.headers["Cache-Control"] = "no-store"
        return job

    @router.get("/by-client/{client_id}", response_model=ResearchJob)
    async def by_client(client_id: str, request: Request, response: Response):
        job = request.app.state.research_jobs.store.find(job_owner(request), client_id)
        if job is None:
            raise HTTPException(404, "Task not found.")
        response.headers["Cache-Control"] = "no-store"
        return job

    return router
