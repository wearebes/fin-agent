from __future__ import annotations

import json
import logging
from typing import Any

from fin_agent.adapters.market_data import MarketDataProvider
from fin_agent.adapters.search import SearchProvider
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.workflows.research.stages import ToolRegistry

logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


class SearchTool:
    def __init__(self, search: SearchProvider) -> None:
        self._search = search

    async def __call__(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results")
        try:
            resp = self._search.search(query, max_results=max_results)
            items = []
            for r in resp.results:
                item: dict[str, Any] = {"title": r.title, "url": r.url}
                if r.text:
                    item["text"] = _truncate(r.text, 2000)
                items.append(item)
            return json.dumps(items, ensure_ascii=False)
        except Exception:
            logger.exception("search tool failed for query=%s", query)
            return json.dumps([])


class MarketDataTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        asset_type = AssetType(kwargs.get("asset_type", "stock"))
        period = kwargs.get("period")
        try:
            resp = self._md.get_market_data(
                ticker, asset_type, frequency=DataFrequency.DAILY, period=period
            )
            rows = [
                {
                    "date": str(p.trade_date),
                    "open": p.open,
                    "high": p.high,
                    "low": p.low,
                    "close": p.close,
                    "volume": p.volume,
                }
                for p in resp.data[-60:]
            ]
            return json.dumps(rows, ensure_ascii=False)
        except Exception:
            logger.exception("market_data tool failed for ticker=%s", ticker)
            return json.dumps([])


class FinancialsTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        stmt_type = FinancialStatementType(
            kwargs.get("statement_type", "income_statement")
        )
        try:
            resp = self._md.get_financials(ticker, stmt_type)
            rows = [r.model_dump(mode="json") for r in resp.data[-8:]]
            return json.dumps(rows, ensure_ascii=False)
        except Exception:
            logger.exception("financials tool failed for ticker=%s", ticker)
            return json.dumps([])


class CompanyInfoTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        try:
            info = self._md.get_company_info(ticker)
            return json.dumps(info.model_dump(mode="json"), ensure_ascii=False)
        except Exception:
            logger.exception("company_info tool failed for ticker=%s", ticker)
            return json.dumps({})


class AnalystTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        try:
            resp = self._md.get_analyst_data(ticker)
            return json.dumps(
                resp.model_dump(mode="json"), ensure_ascii=False
            )
        except Exception:
            logger.exception("analyst tool failed for ticker=%s", ticker)
            return json.dumps({})


class CryptoTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        period = kwargs.get("period")
        try:
            resp = self._md.get_crypto_data(ticker, period=period)
            rows = [
                {
                    "date": str(p.trade_date),
                    "close": p.close,
                    "volume": p.volume,
                    "market_cap": p.market_cap,
                }
                for p in resp.data[-60:]
            ]
            return json.dumps(rows, ensure_ascii=False)
        except Exception:
            logger.exception("crypto tool failed for ticker=%s", ticker)
            return json.dumps([])


def build_default_tool_registry(
    search: SearchProvider,
    market_data: MarketDataProvider,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("search", SearchTool(search))
    registry.register("market_data", MarketDataTool(market_data))
    registry.register("financials", FinancialsTool(market_data))
    registry.register("company_info", CompanyInfoTool(market_data))
    registry.register("analyst", AnalystTool(market_data))
    registry.register("crypto", CryptoTool(market_data))
    return registry
