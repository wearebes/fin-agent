from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from fin_agent.adapters.llm.openai.config import OpenAIConfig
from fin_agent.domain.types import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, config: OpenAIConfig | None = None) -> None:
        self._config = config or OpenAIConfig()
        api_key = (
            self._config.api_key.get_secret_value()
            if self._config.api_key is not None
            else None
        )
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": self._config.timeout_seconds,
        }
        if self._config.base_url is not None:
            kwargs["base_url"] = self._config.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        empty = LLMResponse(
            message=LLMMessage(role="assistant", content=""),
            model=self._config.model,
        )
        try:
            openai_messages: list[dict[str, str]] = [
                {"role": m.role, "content": m.content} for m in messages
            ]
            create_kwargs: dict[str, Any] = {
                "model": self._config.model,
                "messages": openai_messages,
            }
            if temperature is not None:
                create_kwargs["temperature"] = temperature
            else:
                create_kwargs["temperature"] = self._config.temperature
            if max_tokens is not None:
                create_kwargs["max_tokens"] = max_tokens

            response = await self._client.chat.completions.create(**create_kwargs)

            choice = response.choices[0]
            content = choice.message.content or ""
            role = choice.message.role or "assistant"
            usage_prompt = response.usage.prompt_tokens if response.usage else None
            usage_completion = (
                response.usage.completion_tokens if response.usage else None
            )

            return LLMResponse(
                message=LLMMessage(role=role, content=content),
                model=response.model,
                usage_prompt_tokens=usage_prompt,
                usage_completion_tokens=usage_completion,
            )
        except Exception:
            logger.exception("chat failed for model=%s", self._config.model)
            return empty
