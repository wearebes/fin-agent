from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from fin_agent.adapters.llm.openai import OpenAIClient, OpenAIConfig
from fin_agent.domain.types import LLMMessage, LLMResponse


def _make_message(
    role: str = "assistant",
    content: str | None = "Hello!",
) -> MagicMock:
    msg = MagicMock()
    msg.role = role
    msg.content = content
    return msg


def _make_choice(
    message: MagicMock | None = None,
) -> MagicMock:
    choice = MagicMock()
    choice.message = message or _make_message()
    return choice


def _make_usage(
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    return usage


_UNSET = object()


def _make_chat_response(
    choices: list[MagicMock] | None = None,
    model: str = "gpt-4.1-mini",
    usage: MagicMock | None = _UNSET,  # type: ignore[assignment]
) -> MagicMock:
    resp = MagicMock()
    resp.choices = choices or [_make_choice()]
    resp.model = model
    resp.usage = _make_usage() if usage is _UNSET else usage
    return resp


class TestChatSuccess:
    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_converts_messages_and_returns_response(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(
                choices=[_make_choice(_make_message("assistant", "AAPL is a buy."))],
                model="gpt-4.1-mini",
                usage=_make_usage(15, 8),
            )
        )

        client = OpenAIClient()
        messages = [
            LLMMessage(role="system", content="You are a financial analyst."),
            LLMMessage(role="user", content="What about AAPL?"),
        ]
        resp = await client.chat(messages)

        assert isinstance(resp, LLMResponse)
        assert resp.message.role == "assistant"
        assert resp.message.content == "AAPL is a buy."
        assert resp.model == "gpt-4.1-mini"
        assert resp.usage_prompt_tokens == 15
        assert resp.usage_completion_tokens == 8

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_openai_messages_format(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response()
        )

        client = OpenAIClient()
        messages = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="usr"),
            LLMMessage(role="assistant", content="ast"),
        ]
        await client.chat(messages)

        call_kwargs = mock_client.chat.completions.create.call_args
        sent_messages = call_kwargs.kwargs["messages"]
        assert len(sent_messages) == 3
        assert sent_messages[0] == {"role": "system", "content": "sys"}
        assert sent_messages[1] == {"role": "user", "content": "usr"}
        assert sent_messages[2] == {"role": "assistant", "content": "ast"}

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_empty_content_fallback(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        msg = _make_message("assistant", None)
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(
                choices=[_make_choice(msg)],
            )
        )

        client = OpenAIClient()
        resp = await client.chat([LLMMessage(role="user", content="hi")])

        assert resp.message.content == ""

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_no_usage_returns_none_tokens(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(usage=None),
        )

        client = OpenAIClient()
        resp = await client.chat([LLMMessage(role="user", content="hi")])

        assert resp.usage_prompt_tokens is None
        assert resp.usage_completion_tokens is None


class TestChatWithCustomParams:
    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_temperature_override(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response()
        )

        client = OpenAIClient()
        await client.chat(
            [LLMMessage(role="user", content="hi")],
            temperature=0.7,
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["temperature"] == 0.7

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_max_tokens_override(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response()
        )

        client = OpenAIClient()
        await client.chat(
            [LLMMessage(role="user", content="hi")],
            max_tokens=500,
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 500

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_default_temperature_from_config(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response()
        )

        config = OpenAIConfig(temperature=0.5)
        client = OpenAIClient(config=config)
        await client.chat([LLMMessage(role="user", content="hi")])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["temperature"] == 0.5

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_no_max_tokens_when_not_provided(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response()
        )

        client = OpenAIClient()
        await client.chat([LLMMessage(role="user", content="hi")])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert "max_tokens" not in call_kwargs.kwargs


class TestChatErrorHandling:
    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_exception_returns_empty_response(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        client = OpenAIClient()
        resp = await client.chat([LLMMessage(role="user", content="hi")])

        assert isinstance(resp, LLMResponse)
        assert resp.message.role == "assistant"
        assert resp.message.content == ""
        assert resp.model == "gpt-4.1-mini"

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_auth_error_returns_empty_response(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("401 Unauthorized")
        )

        client = OpenAIClient()
        resp = await client.chat([LLMMessage(role="user", content="hi")])

        assert resp.message.content == ""


class TestChatWithBaseUrl:
    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    def test_base_url_passed_to_client(self, mock_openai_cls):
        config = OpenAIConfig(base_url="https://open.bigmodel.cn/api/paas/v4")
        OpenAIClient(config=config)

        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["base_url"] == "https://open.bigmodel.cn/api/paas/v4"

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    def test_no_base_url_when_not_configured(self, mock_openai_cls):
        config = OpenAIConfig()
        OpenAIClient(config=config)

        call_kwargs = mock_openai_cls.call_args
        assert "base_url" not in call_kwargs.kwargs

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_custom_model_name(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(model="glm-5.1"),
        )

        config = OpenAIConfig(model="glm-5.1")
        client = OpenAIClient(config=config)
        resp = await client.chat([LLMMessage(role="user", content="hi")])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "glm-5.1"
        assert resp.model == "glm-5.1"


class TestConfigIntegration:
    def test_default_config(self):
        config = OpenAIConfig()
        assert config.model == "gpt-4.1-mini"
        assert config.api_key is None
        assert config.base_url is None
        assert config.timeout_seconds == 30
        assert config.temperature == 0.1

    def test_custom_config(self):
        config = OpenAIConfig(
            model="glm-5.1",
            api_key=SecretStr("test-key"),
            base_url="https://open.bigmodel.cn/api/paas/v4",
            timeout_seconds=60,
            temperature=0.3,
        )
        assert config.model == "glm-5.1"
        assert config.api_key is not None
        assert config.api_key.get_secret_value() == "test-key"
        assert config.base_url == "https://open.bigmodel.cn/api/paas/v4"
        assert config.timeout_seconds == 60
        assert config.temperature == 0.3

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    def test_api_key_passed_to_client(self, mock_openai_cls):
        config = OpenAIConfig(api_key=SecretStr("sk-test-123"))
        OpenAIClient(config=config)

        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["api_key"] == "sk-test-123"

    @patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI")
    def test_timeout_passed_to_client(self, mock_openai_cls):
        config = OpenAIConfig(timeout_seconds=60)
        OpenAIClient(config=config)

        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["timeout"] == 60
