from __future__ import annotations

from unittest.mock import MagicMock, patch

from fin_agent.adapters.search.exa import ExaSearchClient, ExaSearchConfig
from fin_agent.domain.types import SearchResponse


def _make_exa_result(
    url: str = "https://example.com/article",
    title: str | None = "Test Article",
    score: float | None = 0.95,
    text: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.url = url
    r.title = title
    r.score = score
    r.text = text
    return r


def _make_search_response(results: list[MagicMock] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.results = results or []
    return resp


class TestSearchWithText:
    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_converts_results_to_search_response(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        r1 = _make_exa_result(text="Some content here")
        r2 = _make_exa_result(
            url="https://example.com/other",
            title="Other Article",
            score=0.8,
            text="More content",
        )
        mock_exa.search_and_contents.return_value = _make_search_response([r1, r2])

        client = ExaSearchClient(ExaSearchConfig(api_key="test-key"))
        resp = client.search("AAPL earnings")

        assert isinstance(resp, SearchResponse)
        assert resp.query == "AAPL earnings"
        assert len(resp.results) == 2
        assert resp.results[0].title == "Test Article"
        assert resp.results[0].url == "https://example.com/article"
        assert resp.results[0].text == "Some content here"
        assert resp.results[0].score == 0.95
        assert resp.results[1].title == "Other Article"
        assert resp.results[1].text == "More content"

    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_title_falls_back_to_url_when_none(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        r = _make_exa_result(title=None, text="body")
        mock_exa.search_and_contents.return_value = _make_search_response([r])

        client = ExaSearchClient(ExaSearchConfig(api_key="test-key"))
        resp = client.search("test query")

        assert resp.results[0].title == "https://example.com/article"

    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_uses_search_and_contents_when_include_text_true(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        mock_exa.search_and_contents.return_value = _make_search_response([])

        config = ExaSearchConfig(api_key="test-key", include_text=True)
        client = ExaSearchClient(config=config)
        client.search("test query")

        mock_exa.search_and_contents.assert_called_once_with(
            "test query", text=True, num_results=8
        )
        mock_exa.search.assert_not_called()


class TestSearchWithoutText:
    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_uses_search_when_include_text_false(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        r = _make_exa_result()
        del r.text
        mock_exa.search.return_value = _make_search_response([r])

        config = ExaSearchConfig(api_key="test-key", include_text=False)
        client = ExaSearchClient(config=config)
        resp = client.search("test query")

        mock_exa.search.assert_called_once_with("test query", num_results=8)
        mock_exa.search_and_contents.assert_not_called()
        assert resp.results[0].text is None


class TestSearchErrorHandling:
    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_exception_returns_empty_response(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        mock_exa.search_and_contents.side_effect = Exception("network error")

        client = ExaSearchClient(ExaSearchConfig(api_key="test-key"))
        resp = client.search("test query")

        assert isinstance(resp, SearchResponse)
        assert resp.query == "test query"
        assert len(resp.results) == 0


class TestMaxResultsOverride:
    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_max_results_override(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        mock_exa.search_and_contents.return_value = _make_search_response([])

        client = ExaSearchClient(ExaSearchConfig(api_key="test-key"))
        client.search("test query", max_results=3)

        mock_exa.search_and_contents.assert_called_once_with(
            "test query", text=True, num_results=3
        )

    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_config_max_results_used_as_default(self, mock_exa_cls):
        mock_exa = mock_exa_cls.return_value
        mock_exa.search_and_contents.return_value = _make_search_response([])

        config = ExaSearchConfig(api_key="test-key", max_results=5)
        client = ExaSearchClient(config=config)
        client.search("test query")

        mock_exa.search_and_contents.assert_called_once_with(
            "test query", text=True, num_results=5
        )


class TestConfigIntegration:
    def test_default_config(self):
        config = ExaSearchConfig()
        assert config.max_results == 8
        assert config.include_text is True
        assert config.enabled is True
        assert config.api_key is None

    def test_custom_config(self):
        config = ExaSearchConfig(max_results=3, include_text=False)
        assert config.max_results == 3
        assert config.include_text is False

    @patch("fin_agent.adapters.search.exa.client.Exa")
    def test_api_key_passed_to_exa(self, mock_exa_cls):
        from pydantic import SecretStr

        config = ExaSearchConfig(api_key=SecretStr("my-secret-key"))
        ExaSearchClient(config=config)

        mock_exa_cls.assert_called_once_with(api_key="my-secret-key")

    def test_no_api_key_returns_empty_results(self):
        config = ExaSearchConfig()
        client = ExaSearchClient(config=config)
        resp = client.search("test query")
        assert isinstance(resp, SearchResponse)
        assert len(resp.results) == 0
