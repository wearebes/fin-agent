from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from fin_agent.adapters.llm.openai.client import _to_openai_tool
from fin_agent.adapters.market_data import MarketDataProvider
from fin_agent.adapters.search import SearchProvider
from fin_agent.domain.types import LLMMessage, LLMResponse, ToolDefinition
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext

logger = logging.getLogger(__name__)


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


@runtime_checkable
class ToolFn(Protocol):
    async def __call__(self, **kwargs: Any) -> str: ...


class ToolRegistry:
    """Single source of truth for the tool catalog.

    Backward-compatible upgrade of the original string-keyed registry: it now
    also stores a :class:`ToolDefinition` (with a real JSON Schema) per tool,
    while keeping ``register``/``get``/``available_tools``/``tool_schemas``
    behaviour identical for existing callers.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, name_or_definition: str | ToolDefinition, fn: ToolFn) -> None:
        """Register a tool. Accepts both call shapes:

        - ``register("search", handler)`` — legacy form, auto-builds a minimal
          ``ToolDefinition`` (preserves the original behaviour).
        - ``register(ToolDefinition(name=..., input_schema={...}), handler)`` —
          new form carrying a real JSON Schema.
        """
        if isinstance(name_or_definition, str):
            definition = ToolDefinition(
                name=name_or_definition,
                description=f"Call the {name_or_definition} tool.",
            )
        else:
            definition = name_or_definition
        self._definitions[definition.name] = definition
        self._tools[definition.name] = fn

    def get(self, name: str) -> ToolFn | None:
        return self._tools.get(name)

    def available_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def tool_schemas(self) -> list[dict[str, Any]]:
        # Unchanged method name / return shape for existing callers.
        return [
            {"name": d.name, "description": d.description} for d in self.definitions()
        ]

    def definitions(self) -> list[ToolDefinition]:
        """Full schema view of every registered tool (sorted by name)."""
        return [self._definitions[name] for name in self.available_tools()]

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """One-step conversion, ready to hand to ``chat(tools=...)``."""
        return [_to_openai_tool(d) for d in self.definitions()]

    def merge(self, other: ToolRegistry) -> None:
        """Merge another registry's tools in (future MCP-source entry point)."""
        for name in other.available_tools():
            fn = other.get(name)
            definition = other._definitions.get(name)
            if fn is None or definition is None:
                continue
            if name in self._tools:
                logger.warning(
                    "Tool '%s' redefined by source=%s", name, definition.source
                )
            self.register(definition, fn)


class StageDeps:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        search: SearchProvider,
        market_data: MarketDataProvider,
        tool_registry: ToolRegistry,
        config: ResearchWorkflowConfig,
    ) -> None:
        self.llm = llm
        self.search = search
        self.market_data = market_data
        # Single catalog source: planner, executor, /v1/skills and future MCP
        # all read this one registry.
        self.tool_registry = tool_registry
        self.config = config


@runtime_checkable
class StageFn(Protocol):
    async def __call__(
        self,
        ctx: ResearchContext,
        deps: StageDeps,
    ) -> ResearchContext: ...
