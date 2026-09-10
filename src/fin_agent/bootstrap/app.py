"""FastAPI application factory for the fin-agent scaffold."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from fin_agent.bootstrap.container import Container, build_container
from fin_agent.bootstrap.settings import AppSettings, load_settings
from fin_agent.interfaces.api.auth_router import build_auth_router
from fin_agent.interfaces.api.codex_router import build_codex_router
from fin_agent.interfaces.api.forensics_router import build_forensics_router
from fin_agent.interfaces.api.jobs_router import build_jobs_router
from fin_agent.interfaces.api.local_router import build_local_router
from fin_agent.interfaces.api.model_router import build_model_router
from fin_agent.interfaces.api.router import build_router
from fin_agent.services.research_jobs import ResearchJobs
from fin_agent.storage.job_store import JobStore


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the API app and attach the container during lifespan startup."""
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        container = build_container(resolved_settings)
        app.state.container = container
        job_engine = getattr(container.run_store, "engine", None)
        owns_job_engine = job_engine is None
        if job_engine is None:
            job_engine = create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
            )
        jobs = ResearchJobs(container, JobStore(job_engine))
        app.state.research_jobs = jobs
        jobs.start()
        yield
        await jobs.close()
        if owns_job_engine:
            job_engine.dispose()
        run_store = container.run_store
        if hasattr(run_store, "engine"):
            run_store.engine.dispose()
        user_store = container.user_store
        if hasattr(user_store, "engine"):
            user_store.engine.dispose()
        app.state.container = None

    app = FastAPI(
        title=resolved_settings.app.name,
        lifespan=lifespan,
        docs_url='/docs' if resolved_settings.feature_flags.enable_api_docs else None,
        redoc_url='/redoc' if resolved_settings.feature_flags.enable_api_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.runtime.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router())
    app.include_router(build_auth_router())
    app.include_router(build_forensics_router())
    app.include_router(build_local_router())
    app.include_router(build_model_router())
    app.include_router(build_codex_router())
    app.include_router(build_jobs_router())

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    dist_dir = project_root / "frontend" / "dist"
    static_dir = project_root / "static"

    if dist_dir.is_dir():
        # Serve the built React SPA. Mounted at "/" AFTER the API router so
        # /v1, /healthz, /docs and /openapi.json keep priority. html=True
        # returns index.html for "/", which is all HashRouter needs. The SPA
        # references /assets/* — StaticFiles serves those from dist as well.
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")
    elif static_dir.is_dir():
        # Fallback: legacy single-file frontend.
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app


def create_default_app() -> FastAPI:
    """Create the default app used by the CLI and ASGI server."""
    return create_app()


__all__ = ['Container', 'create_app', 'create_default_app']
