"""Search adapters."""

from __future__ import annotations

from typing import Protocol

from fin_agent.domain.types import SearchResponse


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
    ) -> SearchResponse: ...
