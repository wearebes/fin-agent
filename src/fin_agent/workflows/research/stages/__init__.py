from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fin_agent.adapters.market_data import MarketDataProvider
from fin_agent.adapters.search import SearchProvider
from fin_agent.domain.types import LLMMessage, LLMResponse
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...


class StageDeps:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        search: SearchProvider,
        market_data: MarketDataProvider,
        config: ResearchWorkflowConfig,
    ) -> None:
        self.llm = llm
        self.search = search
        self.market_data = market_data
        self.config = config


@runtime_checkable
class StageFn(Protocol):
    async def __call__(
        self,
        ctx: ResearchContext,
        deps: StageDeps,
    ) -> ResearchContext: ...


@runtime_checkable
class ToolFn(Protocol):
    async def __call__(self, **kwargs: Any) -> str: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> ToolFn | None:
        return self._tools.get(name)

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "description": f"Call the {name} tool."}
            for name in self.available_tools()
        ]
