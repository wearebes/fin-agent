from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from fin_agent.adapters.llm.openai.config import OpenAIConfig
from fin_agent.domain.types import LLMMessage, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


def _to_openai_message(m: LLMMessage) -> dict[str, Any]:
    """Convert an internal ``LLMMessage`` into an OpenAI chat message dict.

    The assistant tool-call turn and the ``role='tool'`` result turn are the
    two shapes that carry the multi-turn function-calling protocol; every other
    message is a plain ``{role, content}`` dict (byte-for-byte identical to the
    pre-tool-calling behaviour).
    """
    if m.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": m.tool_call_id or "",
            "content": m.content,
        }

    msg: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        # OpenAI requires `arguments` to be a JSON *string*, not a dict.
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in m.tool_calls
        ]
        # An assistant turn that only requests tools may have empty content;
        # OpenAI accepts content=None in that case.
        if not m.content:
            msg["content"] = None
    return msg


def _from_openai_message(msg: Any) -> LLMMessage:
    """Convert an OpenAI ``choice.message`` into an internal ``LLMMessage``.

    ``function.arguments`` arrives as a JSON string and is decoded into a dict;
    a decode failure is logged and degrades to ``arguments={}`` rather than
    failing the whole response.
    """
    raw_calls = getattr(msg, "tool_calls", None)
    tool_calls: list[ToolCall] | None = None
    if raw_calls:
        tool_calls = []
        for rc in raw_calls:
            fn = rc.function
            try:
                arguments = json.loads(fn.arguments) if fn.arguments else {}
                if not isinstance(arguments, dict):
                    arguments = {}
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Failed to decode tool arguments for call=%s name=%s",
                    getattr(rc, "id", "?"),
                    getattr(fn, "name", "?"),
                )
                arguments = {}
            tool_calls.append(
                ToolCall(id=rc.id, name=fn.name, arguments=arguments)
            )

    return LLMMessage(
        role=msg.role or "assistant",
        content=msg.content or "",
        tool_calls=tool_calls,
    )


def _to_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a ``ToolDefinition`` into an OpenAI ``tools=[...]`` entry.

    The ``input_schema`` is passed straight through as ``function.parameters``;
    whether it was hand-written or produced by a future MCP ``tools/list``
    response, the shape is identical — this is the root reason the registry can
    serve as the MCP seam.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


class OpenAIClient:
    def __init__(self, config: OpenAIConfig | None = None) -> None:
        self._config = config or OpenAIConfig()
        self._client = self._make_client(self._config)

    @staticmethod
    def _make_client(config: OpenAIConfig) -> AsyncOpenAI | None:
        api_key = (
            config.api_key.get_secret_value()
            if config.api_key is not None
            else None
        )
        if not api_key:
            return None
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": config.timeout_seconds,
        }
        if config.base_url is not None:
            kwargs["base_url"] = config.base_url
        return AsyncOpenAI(**kwargs)

    def reconfigure(self, config: OpenAIConfig) -> None:
        """Apply a locally saved provider configuration without revealing its secret."""
        self._config = config
        self._client = self._make_client(config)

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        empty = LLMResponse(
            message=LLMMessage(role="assistant", content=""),
            model=self._config.model,
        )
        if self._client is None:
            logger.warning("chat skipped because no local OpenAI API key is configured")
            return empty
        try:
            openai_messages = [_to_openai_message(m) for m in messages]
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
            if tools:
                create_kwargs["tools"] = [_to_openai_tool(t) for t in tools]
                if tool_choice is not None:
                    create_kwargs["tool_choice"] = tool_choice

            response = await self._client.chat.completions.create(**create_kwargs)

            if not response.choices:
                logger.warning("LLM returned empty choices for model=%s", self._config.model)
                return empty

            choice = response.choices[0]
            message = _from_openai_message(choice.message)
            usage_prompt = response.usage.prompt_tokens if response.usage else None
            usage_completion = (
                response.usage.completion_tokens if response.usage else None
            )

            return LLMResponse(
                message=message,
                model=response.model,
                usage_prompt_tokens=usage_prompt,
                usage_completion_tokens=usage_completion,
                finish_reason=choice.finish_reason,
            )
        except Exception:
            logger.exception("chat failed for model=%s", self._config.model)
            return empty
