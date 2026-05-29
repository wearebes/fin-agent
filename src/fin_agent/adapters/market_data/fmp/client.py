from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import requests

from fin_agent.adapters.market_data.fmp.config import FMPConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystRecommendation,
    CompanyInfo,
    CryptoDataPoint,
    EarningsEstimate,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataPoint,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

_FREQUENCY_SERIES: dict[DataFrequency, str] = {
    DataFrequency.DAILY: "",
    DataFrequency.WEEKLY: "",
    DataFrequency.MONTHLY: "",
}

_STATEMENT_EP: dict[FinancialStatementType, str] = {
    FinancialStatementType.INCOME_STATEMENT: "income-statement",
    FinancialStatementType.BALANCE_SHEET: "balance-sheet-statement",
    FinancialStatementType.CASH_FLOW: "cash-flow-statement",
}


class FMPClient:
    def __init__(self, config: FMPConfig | None = None) -> None:
        self._config = config or FMPConfig()
        self._api_key = (
            self._config.api_key.get_secret_value()
            if self._config.api_key is not None
            else None
        )
        if not self._api_key:
            logger.warning("FMPClient: no API key configured, all calls will return empty")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._api_key:
            return None
        p = dict(params or {})
        p["apikey"] = self._api_key
        url = f"{self._config.base_url}/{path}"
        try:
            r = requests.get(url, params=p, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception:
            logger.exception("FMP request failed: %s", url)
            return None

    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        empty = MarketDataResponse(ticker=ticker, asset_type=asset_type, frequency=frequency)
        days = _period_days(period or "1y")
        end = date.today()
        start = end - timedelta(days=days)

        if asset_type == AssetType.CRYPTO:
            return self._crypto_history(ticker, start, end, empty)

        path = f"historical-price-full/{ticker}"
        data = self._get(path, {"from": start.isoformat(), "to": end.isoformat()})
        if not data or "historical" not in data:
            return empty

        points: list[MarketDataPoint] = []
        for item in data["historical"]:
            points.append(
                MarketDataPoint(
                    ticker=ticker,
                    asset_type=asset_type,
                    trade_date=date.fromisoformat(item["date"]),
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=int(item.get("volume", 0) or 0),
                )
            )
        return MarketDataResponse(ticker=ticker, asset_type=asset_type, frequency=frequency, data=points)

    def _crypto_history(
        self, ticker: str, start: date, end: date, empty: MarketDataResponse
    ) -> MarketDataResponse:
        symbol = ticker.replace("-", "")
        data = self._get(
            f"historical-price-full/{symbol}",
            {"from": start.isoformat(), "to": end.isoformat()},
        )
        if not data or "historical" not in data:
            return empty
        points: list[MarketDataPoint] = []
        for item in data["historical"]:
            points.append(
                MarketDataPoint(
                    ticker=ticker,
                    asset_type=AssetType.CRYPTO,
                    trade_date=date.fromisoformat(item["date"]),
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=int(item.get("volume", 0) or 0),
                )
            )
        return MarketDataResponse(ticker=ticker, asset_type=AssetType.CRYPTO, frequency=empty.frequency, data=points)

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType = FinancialStatementType.INCOME_STATEMENT,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        empty = FinancialStatementResponse(ticker=ticker, statement_type=statement_type, frequency=frequency)
        ep = _STATEMENT_EP.get(statement_type)
        if not ep:
            return empty
        period_param = "quarter" if frequency == DataFrequency.QUARTERLY else "annual"
        data = self._get(f"{ep}/{ticker}", {"period": period_param})
        if not data or not isinstance(data, list):
            return empty
        records: list[FinancialStatementRecord] = []
        for item in data[:8]:
            records.append(
                FinancialStatementRecord(
                    ticker=ticker,
                    end_date=item.get("date", item.get("fillingDate", "")),
                    total_revenue=_safe_float(item.get("revenue")),
                    net_income=_safe_float(item.get("netIncome")),
                    total_assets=_safe_float(item.get("totalAssets")),
                    total_liabilities=_safe_float(item.get("totalLiabilities")),
                    operating_cash_flow=_safe_float(item.get("operatingCashFlow")),
                    free_cash_flow=_safe_float(item.get("freeCashFlow")),
                )
            )
        return FinancialStatementResponse(ticker=ticker, statement_type=statement_type, frequency=frequency, records=records)

    def get_company_info(self, ticker: str) -> CompanyInfo | None:
        data = self._get(f"profile/{ticker}")
        if not data or not isinstance(data, list) or not data:
            return None
        p = data[0]
        return CompanyInfo(
            ticker=ticker,
            name=p.get("companyName", ""),
            sector=p.get("sector", ""),
            industry=p.get("industry", ""),
            description=p.get("description", ""),
            market_cap=_safe_int(p.get("mktCap")),
            exchange=p.get("exchangeShortName", ""),
        )

    def get_analyst_data(self, ticker: str) -> list[AnalystRecommendation]:
        data = self._get(f"analyst-estimate-consensus/{ticker}")
        if not data or not isinstance(data, list):
            return []
        recs: list[AnalystRecommendation] = []
        for item in data[:5]:
            recs.append(
                AnalystRecommendation(
                    ticker=ticker,
                    date=item.get("date", ""),
                    recommendation=item.get("consensus", ""),
                    target_price=_safe_float(item.get("targetPrice")),
                )
            )
        return recs

    def get_crypto_data(self, ticker: str) -> list[CryptoDataPoint]:
        resp = self.get_market_data(ticker, AssetType.CRYPTO, period="1mo")
        return [
            CryptoDataPoint(
                ticker=pt.ticker,
                trade_date=pt.trade_date,
                open=pt.open,
                high=pt.high,
                low=pt.low,
                close=pt.close,
                volume=pt.volume,
            )
            for pt in resp.data
        ]


def _period_days(period: str) -> int:
    mapping = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}
    return mapping.get(period, 365)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
