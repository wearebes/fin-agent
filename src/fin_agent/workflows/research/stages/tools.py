from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fin_agent.adapters.market_data import MarketDataProvider
from fin_agent.adapters.search import SearchProvider
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import ToolDefinition
from fin_agent.workflows.research.evidence import compact_records, format_financials
from fin_agent.workflows.research.stages import ToolRegistry
from fin_agent.workflows.research.tool_inputs import (
    CryptoInput,
    FinancialsInput,
    MarketDataInput,
    SearchInput,
    TickerInput,
)

logger = logging.getLogger(__name__)

_ASSET_TYPES = [a.value for a in AssetType]
_STATEMENT_TYPES = [s.value for s in FinancialStatementType]


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
            resp = await asyncio.to_thread(self._search.search, query, max_results=max_results)
            items = []
            for r in resp.results:
                item: dict[str, Any] = {"title": r.title, "url": r.url}
                if r.text:
                    item["text"] = _truncate(r.text, 2000)
                items.append(item)
            return compact_records(items)
        except Exception:
            logger.exception("search tool failed for query=%s", query)
            return "[]"


class MarketDataTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        asset_type = AssetType(kwargs.get("asset_type", "stock"))
        period = kwargs.get("period")
        try:
            resp = await asyncio.to_thread(
                self._md.get_market_data,
                ticker,
                asset_type,
                frequency=DataFrequency(kwargs.get("frequency", "daily")),
                period=period,
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
            return compact_records(rows)
        except Exception:
            logger.exception("market_data tool failed for ticker=%s", ticker)
            return "[]"


class FinancialsTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        stmt_type = FinancialStatementType(kwargs.get("statement_type", "income_statement"))
        try:
            resp = await asyncio.to_thread(
                self._md.get_financials,
                ticker,
                stmt_type,
                frequency=DataFrequency(kwargs.get("frequency", "yearly")),
            )
            return format_financials(resp.data)
        except Exception:
            logger.exception("financials tool failed for ticker=%s", ticker)
            return "[]"


class CompanyInfoTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        try:
            info = await asyncio.to_thread(self._md.get_company_info, ticker)
            if not info.model_dump(exclude_none=True, exclude={"ticker"}):
                return "{}"
            return json.dumps(info.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
        except Exception:
            logger.exception("company_info tool failed for ticker=%s", ticker)
            return "{}"


class AnalystTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        try:
            resp = await asyncio.to_thread(self._md.get_analyst_data, ticker)
            if not resp.recommendations and not resp.earnings_estimates:
                return "{}"
            return json.dumps(resp.model_dump(mode="json"), ensure_ascii=False)
        except Exception:
            logger.exception("analyst tool failed for ticker=%s", ticker)
            return "{}"


class CryptoTool:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self._md = market_data

    async def __call__(self, **kwargs: Any) -> str:
        ticker = kwargs.get("ticker", "")
        period = kwargs.get("period")
        try:
            resp = await asyncio.to_thread(self._md.get_crypto_data, ticker, period=period)
            rows = [
                {
                    "date": str(p.trade_date),
                    "close": p.close,
                    "volume": p.volume,
                    "market_cap": p.market_cap,
                }
                for p in resp.data[-60:]
            ]
            return compact_records(rows)
        except Exception:
            logger.exception("crypto tool failed for ticker=%s", ticker)
            return "[]"


def build_default_tool_registry(
    search: SearchProvider,
    market_data: MarketDataProvider,
) -> ToolRegistry:
    registry = ToolRegistry()
    if getattr(search, "configured", True):
        registry.register(
            ToolDefinition(
                name="search",
                description=(
                    "Search the web for current information relevant to the research question."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return.",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
            SearchTool(search),
            SearchInput,
        )
    registry.register(
        ToolDefinition(
            name="market_data",
            description=("Fetch recent OHLCV market data (price/volume history) for a ticker."),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker symbol, e.g. AAPL or 600519.SS.",
                    },
                    "asset_type": {
                        "type": "string",
                        "enum": _ASSET_TYPES,
                        "default": "stock",
                        "description": "Type of the asset.",
                    },
                    "period": {
                        "type": "string",
                        "description": "Lookback period, e.g. '1y', '6mo', '1mo'.",
                    },
                },
                "required": ["ticker"],
            },
        ),
        MarketDataTool(market_data),
        MarketDataInput,
    )
    registry.register(
        ToolDefinition(
            name="financials",
            description=(
                "Fetch financial statements (income statement / balance sheet / "
                "cash flow) for a ticker."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker symbol.",
                    },
                    "statement_type": {
                        "type": "string",
                        "enum": _STATEMENT_TYPES,
                        "default": "income_statement",
                        "description": "Which financial statement to fetch.",
                    },
                },
                "required": ["ticker"],
            },
        ),
        FinancialsTool(market_data),
        FinancialsInput,
    )
    registry.register(
        ToolDefinition(
            name="company_info",
            description=(
                "Fetch company profile: name, sector, industry, market cap and "
                "business description."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker symbol.",
                    },
                },
                "required": ["ticker"],
            },
        ),
        CompanyInfoTool(market_data),
        TickerInput,
    )
    registry.register(
        ToolDefinition(
            name="analyst",
            description=("Fetch analyst recommendations and earnings estimates for a ticker."),
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker symbol.",
                    },
                },
                "required": ["ticker"],
            },
        ),
        AnalystTool(market_data),
        TickerInput,
    )
    registry.register(
        ToolDefinition(
            name="crypto",
            description="Fetch recent price/volume data for a crypto asset.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC-USD.",
                    },
                    "period": {
                        "type": "string",
                        "description": "Lookback period, e.g. '1y', '6mo'.",
                    },
                },
                "required": ["ticker"],
            },
        ),
        CryptoTool(market_data),
        CryptoInput,
    )
    return registry
