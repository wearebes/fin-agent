"""LLM adapters."""

from __future__ import annotations

from typing import Protocol

from fin_agent.domain.types import LLMMessage, LLMResponse, ToolDefinition


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse: ...
