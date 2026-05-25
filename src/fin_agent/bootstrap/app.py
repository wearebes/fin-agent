"""FastAPI application factory for the fin-agent scaffold."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fin_agent.bootstrap.container import Container, build_container
from fin_agent.bootstrap.settings import AppSettings, load_settings
from fin_agent.interfaces.api.router import build_router


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the API app and attach the container during lifespan startup."""
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.container = build_container(resolved_settings)
        yield
        app.state.container = None

    app = FastAPI(
        title=resolved_settings.app.name,
        lifespan=lifespan,
        docs_url='/docs' if resolved_settings.feature_flags.enable_api_docs else None,
        redoc_url='/redoc' if resolved_settings.feature_flags.enable_api_docs else None,
    )
    app.include_router(build_router())
    return app


def create_default_app() -> FastAPI:
    """Create the default app used by the CLI and ASGI server."""
    return create_app()


__all__ = ['Container', 'create_app', 'create_default_app']
