"""Temporary, account-scoped model credentials; never persisted to run records."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from fin_agent.adapters.llm.anthropic import AnthropicClient
from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.adapters.llm.openai.config import OpenAIConfig


class PersonalModelConfig(OpenAIConfig):
    protocol: Literal["openai", "anthropic"] = "openai"
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_url: str = Field(min_length=1, max_length=512)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._:/-]+$")
    api_key: SecretStr = Field(min_length=1, max_length=4096)
    protocol: Literal["openai", "anthropic"] = "openai"
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise ValueError("Invalid credential format")
        return SecretStr(key)


@dataclass(frozen=True)
class ModelConnection:
    config: PersonalModelConfig = field(repr=False)
    expires_at: datetime

    def metadata(self) -> dict[str, str]:
        return {
            "base_url": self.config.base_url or "",
            "model": self.config.model,
            "expires_at": self.expires_at.isoformat(),
            "protocol": self.config.protocol,
            "token_parameter": self.config.token_parameter,
        }


class ModelConnections:
    def __init__(
        self,
        allowed_hosts: list[str],
        *,
        ttl_hours: int = 24,
        proxy_url: str | None = None,
    ) -> None:
        self.allowed_hosts = sorted({host.lower() for host in allowed_hosts})
        self._proxy_url = proxy_url
        self._ttl = timedelta(hours=ttl_hours)
        self._connections: dict[str, ModelConnection] = {}

    def configure(self, payload: ConnectionInput) -> PersonalModelConfig:
        url = urlsplit(payload.base_url)
        if (
            url.scheme != "https"
            or url.hostname not in self.allowed_hosts
            or url.port not in (None, 443)
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(char.isspace() for char in payload.base_url)
            or "\\" in payload.base_url
        ):
            raise ValueError("Use an HTTPS URL on an administrator-approved host, port 443.")
        path = url.path.rstrip("/")
        if path.endswith(("/chat/completions", "/responses", "/messages")):
            raise ValueError("Enter the API base URL, not the completion endpoint.")
        return PersonalModelConfig(
            base_url=urlunsplit((url.scheme, url.netloc, path, "", "")),
            model=payload.model,
            api_key=payload.api_key,
            protocol=payload.protocol,
            token_parameter=payload.token_parameter,
        )

    def get(self, user_id: str) -> ModelConnection | None:
        now = datetime.now(UTC)
        self._connections = {
            key: value for key, value in self._connections.items() if value.expires_at > now
        }
        return self._connections.get(user_id)

    def save(self, user_id: str, config: PersonalModelConfig) -> ModelConnection:
        self.get(user_id)
        if user_id not in self._connections and len(self._connections) >= 1000:
            raise ValueError("Connection capacity reached; try again later.")
        connection = ModelConnection(config, datetime.now(UTC) + self._ttl)
        self._connections[user_id] = connection
        return connection

    def remove(self, user_id: str) -> None:
        self._connections.pop(user_id, None)

    @asynccontextmanager
    async def client(
        self,
        config: PersonalModelConfig,
    ) -> AsyncIterator[OpenAIClient | AnthropicClient]:
        # Only explicit administrator proxy settings are trusted; never forward keys on redirects.
        async with httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            proxy=self._proxy_url,
        ) as transport:
            client = (
                AnthropicClient(config, transport)
                if config.protocol == "anthropic"
                else OpenAIClient(
                    config,
                    http_client=transport,
                    max_retries=0,
                    send_temperature=False,
                    token_parameter=config.token_parameter,
                )
            )
            try:
                yield client
            finally:
                await client.close()
