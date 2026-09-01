from fin_agent.domain.types import LLMMessage, LLMResponse


class DisabledLLM:
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise RuntimeError("System model is disabled; select a personal model connection.")
