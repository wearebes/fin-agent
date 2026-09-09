"""Local-only onboarding and workspace persistence endpoints.

The desktop launcher binds the API to 127.0.0.1. These routes deliberately
keep configuration and conversation data on that same computer.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr, field_validator

from fin_agent.adapters.llm.openai.config import OpenAIConfig
from fin_agent.services.auth import AuthService
from fin_agent.storage.user_store import SQLAlchemyUserStore

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ENV_PATH = _PROJECT_ROOT / ".env"
_LOCAL_DB_PATH = _PROJECT_ROOT / "var" / "fin_agent-local.db"
_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=.*$")


class LocalSetupStatus(BaseModel):
    configured: bool
    workspace_persistent: bool = True
    auth_persistent: bool


class LocalSetupRequest(BaseModel):
    api_key: str | None = Field(default=None, min_length=8, max_length=512)
    model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=512)

    @field_validator("api_key", "model", "base_url")
    @classmethod
    def reject_line_breaks(cls, value: str | None) -> str | None:
        if value is not None and ("\n" in value or "\r" in value):
            raise ValueError("配置内容不能包含换行。")
        return value


class WorkspacePayload(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


def _has_key(config: OpenAIConfig) -> bool:
    return config.api_key is not None and bool(config.api_key.get_secret_value().strip())


def _write_env(updates: dict[str, str]) -> None:
    """Update only the requested local settings; never return their values."""
    existing = _ENV_PATH.read_text(encoding="utf-8").splitlines() if _ENV_PATH.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in existing:
        match = _ENV_LINE.match(line)
        key = match.group(1) if match else None
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    if remaining:
        if output and output[-1]:
            output.append("")
        output.extend(f"{key}={value}" for key, value in remaining.items())
    _ENV_PATH.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _workspace_connection() -> sqlite3.Connection:
    _LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_LOCAL_DB_PATH)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS local_workspace (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return connection


def _ensure_sql_user_store(request: Request) -> None:
    """Make local accounts durable immediately after onboarding."""
    container = request.app.state.container
    if hasattr(container.user_store, "engine"):
        return
    store = SQLAlchemyUserStore("sqlite:///./var/fin_agent-local.db")
    store.create_tables()
    container.user_store = store
    container.auth_service = AuthService(store, container.auth_service._config)


def build_local_router() -> APIRouter:
    router = APIRouter(prefix="/v1/local", tags=["local"])

    @router.get("/setup/status", response_model=LocalSetupStatus)
    def setup_status(request: Request) -> LocalSetupStatus:
        container = request.app.state.container
        return LocalSetupStatus(
            configured=_has_key(container.settings.openai),
            auth_persistent=hasattr(container.user_store, "engine"),
        )

    @router.post("/setup", response_model=LocalSetupStatus)
    def save_setup(payload: LocalSetupRequest, request: Request) -> LocalSetupStatus:
        container = request.app.state.container
        current = container.settings.openai
        api_key = payload.api_key.strip() if payload.api_key else None
        if not api_key and not _has_key(current):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="请填入自己的 API Key。",
            )

        base_url = payload.base_url.strip() if payload.base_url else None
        updates = {
            "FIN_AGENT__OPENAI__MODEL": payload.model.strip(),
            "FIN_AGENT__DATABASE__BACKEND": "sql",
            "FIN_AGENT__DATABASE__URL": "sqlite:///./var/fin_agent-local.db",
        }
        if api_key:
            updates["FIN_AGENT__OPENAI__API_KEY"] = api_key
        if payload.base_url is not None:
            updates["FIN_AGENT__OPENAI__BASE_URL"] = base_url or ""
        _write_env(updates)

        new_config = current.model_copy(
            update={
                "model": payload.model.strip(),
                "base_url": base_url,
                "api_key": SecretStr(api_key) if api_key else current.api_key,
            }
        )
        container.settings.openai = new_config
        container.settings.database.backend = "sql"
        container.settings.database.url = "sqlite:///./var/fin_agent-local.db"
        container.llm.reconfigure(new_config)
        _ensure_sql_user_store(request)
        return LocalSetupStatus(configured=True, auth_persistent=True)

    @router.get("/workspace", response_model=WorkspacePayload | None)
    def load_workspace() -> WorkspacePayload | None:
        with _workspace_connection() as connection:
            row = connection.execute("SELECT payload FROM local_workspace WHERE id = 1").fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return WorkspacePayload(payload=value if isinstance(value, dict) else {})

    @router.put("/workspace", response_model=WorkspacePayload)
    def save_workspace(body: WorkspacePayload) -> WorkspacePayload:
        serialized = json.dumps(body.payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 8_000_000:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="本地会话数据超过 8 MB，请删除不需要的会话后重试。",
            )
        with _workspace_connection() as connection:
            connection.execute(
                "INSERT INTO local_workspace (id, payload, updated_at) "
                "VALUES (1, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(id) DO UPDATE SET "
                "payload=excluded.payload, updated_at=CURRENT_TIMESTAMP",
                (serialized,),
            )
        return body

    return router
