from __future__ import annotations

import logging
from typing import Any

from exa_py import Exa

from fin_agent.adapters.search.exa.config import ExaSearchConfig
from fin_agent.domain.types import SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)


class ExaSearchClient:
    def __init__(self, config: ExaSearchConfig | None = None) -> None:
        self._config = config or ExaSearchConfig()
        api_key = (
            self._config.api_key.get_secret_value()
            if self._config.api_key is not None
            else None
        )
        if api_key:
            self._exa = Exa(api_key=api_key)
        else:
            self._exa = None
            logger.warning("ExaSearchClient: no API key configured, search will return empty results")

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
    ) -> SearchResponse:
        if self._exa is None:
            return SearchResponse(query=query)
        num_results = max_results or self._config.max_results
        include_text = self._config.include_text
        try:
            if include_text:
                raw: Any = self._exa.search_and_contents(
                    query,
                    text=True,
                    num_results=num_results,
                )
            else:
                raw = self._exa.search(
                    query,
                    num_results=num_results,
                )
            items: list[SearchResultItem] = []
            for r in raw.results:
                items.append(
                    SearchResultItem(
                        title=r.title or r.url,
                        url=r.url,
                        text=getattr(r, "text", None),
                        score=r.score,
                    )
                )
            return SearchResponse(query=query, results=items)
        except Exception:
            logger.exception("search failed for query=%s", query)
            return SearchResponse(query=query)
