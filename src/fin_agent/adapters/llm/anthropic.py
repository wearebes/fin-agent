"""Text-only Anthropic Messages adapter using the existing HTTP dependency."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from fin_agent.adapters.llm.openai.config import OpenAIConfig
from fin_agent.domain.types import LLMMessage, LLMResponse, ToolDefinition

logger = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self, config: OpenAIConfig, transport: httpx.AsyncClient) -> None:
        self._config = config
        self._transport = transport

    async def _request(self, messages: list[LLMMessage], max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
                if message.role != "system"
            ],
        }
        system = "\n\n".join(message.content for message in messages if message.role == "system")
        if system:
            payload["system"] = system
        response = await self._transport.post(
            f"{self._config.base_url}/messages",
            json=payload,
            headers={
                "x-api-key": self._config.api_key.get_secret_value()
                if self._config.api_key
                else "",
                "anthropic-version": "2023-06-01",
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise ValueError("Invalid Messages response")
        return data

    async def check_connection(self) -> None:
        data = await self._request([LLMMessage(role="user", content="Reply OK.")], 128)
        if not any(
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and block["text"].strip()
            for block in data["content"]
        ):
            raise ValueError("Messages response contains no text.")

    async def close(self) -> None:
        await self._transport.aclose()

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        try:
            data = await self._request(messages, max_tokens or 4096)
            content = "\n".join(
                block["text"] for block in data["content"] if block["type"] == "text"
            )
            usage = data.get("usage", {})
            return LLMResponse(
                message=LLMMessage(role="assistant", content=content),
                model=data.get("model", self._config.model),
                usage_prompt_tokens=usage.get("input_tokens"),
                usage_completion_tokens=usage.get("output_tokens"),
            )
        except Exception as exc:
            logger.warning("Messages request failed: %s", type(exc).__name__)
            return LLMResponse(
                message=LLMMessage(role="assistant", content=""),
                model=self._config.model,
            )
