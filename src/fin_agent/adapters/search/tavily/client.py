from __future__ import annotations

import logging
from typing import Any

from tavily import TavilyClient

from fin_agent.adapters.search.tavily.config import TavilySearchConfig
from fin_agent.domain.types import SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)


class TavilySearchClient:
    def __init__(self, config: TavilySearchConfig | None = None) -> None:
        self._config = config or TavilySearchConfig()
        api_key = (
            self._config.api_key.get_secret_value()
            if self._config.api_key is not None
            else None
        )
        if api_key:
            self._client = TavilyClient(api_key=api_key)
        else:
            self._client = None
            logger.warning("TavilySearchClient: no API key configured, search will return empty results")

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
    ) -> SearchResponse:
        if self._client is None:
            return SearchResponse(query=query)
        num_results = max_results or self._config.max_results
        try:
            raw: dict[str, Any] = self._client.search(
                query,
                max_results=num_results,
                search_depth=self._config.search_depth,
                include_raw_content=self._config.include_raw_content,
            )
            items: list[SearchResultItem] = []
            for r in raw.get("results", []):
                items.append(
                    SearchResultItem(
                        title=r.get("title", r.get("url", "")),
                        url=r.get("url", ""),
                        text=r.get("content"),
                        score=r.get("score"),
                    )
                )
            return SearchResponse(query=query, results=items)
        except Exception:
            logger.exception("Tavily search failed for query=%s", query)
            return SearchResponse(query=query)
