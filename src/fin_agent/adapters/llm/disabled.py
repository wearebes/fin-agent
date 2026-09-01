from fin_agent.domain.types import LLMMessage, LLMResponse, ToolDefinition


class DisabledLLM:
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        raise RuntimeError("System model is disabled; select a personal model connection.")
