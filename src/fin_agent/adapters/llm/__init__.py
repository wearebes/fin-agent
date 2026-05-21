"""LLM adapters."""

from __future__ import annotations

from typing import Protocol

from fin_agent.domain.types import LLMMessage, LLMResponse


class LLMProvider(Protocol):
    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...
