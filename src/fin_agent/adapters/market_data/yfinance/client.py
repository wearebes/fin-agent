from __future__ import annotations

import logging
from datetime import date
from typing import Any

import yfinance as yf

from fin_agent.adapters.market_data.yfinance.config import YFinanceConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystRecommendation,
    AnalystResponse,
    CompanyInfo,
    CryptoDataPoint,
    CryptoDataResponse,
    EarningsEstimate,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataPoint,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

_FREQUENCY_INTERVAL: dict[DataFrequency, str] = {
    DataFrequency.DAILY: "1d",
    DataFrequency.WEEKLY: "1wk",
    DataFrequency.MONTHLY: "1mo",
    DataFrequency.QUARTERLY: "3mo",
    DataFrequency.YEARLY: "1mo",
}

_INCOME_METRICS: dict[str, list[str]] = {
    "total_revenue": ["Total Revenue", "TotalRevenue"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "NetIncome"],
}

_BALANCE_METRICS: dict[str, list[str]] = {
    "total_assets": ["Total Assets", "TotalAssets"],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
        "TotalLiabilities",
    ],
    "total_equity": [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "TotalEquityGrossMinorityInterest",
    ],
}

_CASHFLOW_METRICS: dict[str, list[str]] = {
    "operating_cash_flow": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "OperatingCashFlow",
    ],
    "free_cash_flow": ["Free Cash Flow", "FreeCashFlow"],
}


def _nan_safe(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _int_safe(value: Any) -> int | None:
    v = _nan_safe(value)
    return None if v is None else int(v)


def _pick_metric(df: Any, names: list[str], col: int) -> float | None:
    for name in names:
        if name in df.index:
            return _nan_safe(df.iloc[df.index.get_loc(name), col])
    return None


def _trade_date(idx: Any) -> date:
    if hasattr(idx, "date"):
        return date(idx.year, idx.month, idx.day)
    return date(idx.year, idx.month, idx.day)


def _yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _margin(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


class YFinanceClient:
    def __init__(self, config: YFinanceConfig | None = None) -> None:
        self._config = config or YFinanceConfig()

    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        empty = MarketDataResponse(
            ticker=ticker, asset_type=asset_type, frequency=frequency
        )
        try:
            t = yf.Ticker(ticker)
            interval = _FREQUENCY_INTERVAL.get(frequency, "1d")
            hist = t.history(
                period=period or self._config.history_period, interval=interval
            )
            if hist is None or hist.empty:
                return empty
            points: list[MarketDataPoint] = []
            for idx, row in hist.iterrows():
                points.append(
                    MarketDataPoint(
                        ticker=ticker,
                        asset_type=asset_type,
                        trade_date=_trade_date(idx),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=_int_safe(row.get("Volume")),
                    )
                )
            return MarketDataResponse(
                ticker=ticker, asset_type=asset_type, frequency=frequency, data=points
            )
        except Exception:
            logger.exception("get_market_data failed for ticker=%s", ticker)
            return empty

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        empty = FinancialStatementResponse(
            ticker=ticker, statement_type=statement_type
        )
        try:
            t = yf.Ticker(ticker)
            is_quarterly = frequency == DataFrequency.QUARTERLY
            df = self._get_statement_df(t, statement_type, is_quarterly)
            if df is None or df.empty:
                return empty
            metric_map = self._metric_map_for(statement_type)
            col_indices = list(range(len(df.columns)))
            col_indices.reverse()
            records: list[FinancialStatementRecord] = []
            prev: dict[str, float | None] = {}
            for col_idx in col_indices:
                col_date = df.columns[col_idx]
                fiscal_year = col_date.year
                fiscal_quarter = (
                    (col_date.month - 1) // 3 + 1 if is_quarterly else None
                )
                cur: dict[str, float | None] = {
                    k: _pick_metric(df, v, col_idx) for k, v in metric_map.items()
                }
                records.append(
                    FinancialStatementRecord(
                        ticker=ticker,
                        statement_type=statement_type,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        total_revenue=cur.get("total_revenue"),
                        net_income=cur.get("net_income"),
                        total_assets=cur.get("total_assets"),
                        total_liabilities=cur.get("total_liabilities"),
                        total_equity=cur.get("total_equity"),
                        operating_cash_flow=cur.get("operating_cash_flow"),
                        free_cash_flow=cur.get("free_cash_flow"),
                        revenue_yoy=_yoy(
                            cur.get("total_revenue"), prev.get("total_revenue")
                        ),
                        net_profit_margin=_margin(
                            cur.get("net_income"), cur.get("total_revenue")
                        ),
                    )
                )
                prev = cur
            records.reverse()
            return FinancialStatementResponse(
                ticker=ticker, statement_type=statement_type, data=records
            )
        except Exception:
            logger.exception("get_financials failed for ticker=%s", ticker)
            return empty

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        empty = AnalystResponse(ticker=ticker)
        try:
            t = yf.Ticker(ticker)
            recs = self._parse_recommendations(t, ticker)
            estimates = self._parse_earnings(t, ticker)
            return AnalystResponse(
                ticker=ticker,
                recommendations=recs,
                earnings_estimates=estimates,
            )
        except Exception:
            logger.exception("get_analyst_data failed for ticker=%s", ticker)
            return empty

    def get_company_info(self, ticker: str) -> CompanyInfo:
        try:
            t = yf.Ticker(ticker)
            info: dict[str, Any] = t.info or {}
            fy_raw = info.get("foundedYear")
            founded_year = _int_safe(fy_raw) if fy_raw is not None else None
            return CompanyInfo(
                ticker=ticker,
                name=info.get("longName") or info.get("shortName"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                country=info.get("country"),
                market_cap=_nan_safe(info.get("marketCap")),
                description=info.get("longBusinessSummary"),
                employees=_int_safe(info.get("fullTimeEmployees")),
                founded_year=founded_year,
            )
        except Exception:
            logger.exception("get_company_info failed for ticker=%s", ticker)
            return CompanyInfo(ticker=ticker)

    def get_crypto_data(
        self,
        ticker: str,
        *,
        period: str | None = None,
    ) -> CryptoDataResponse:
        empty = CryptoDataResponse(ticker=ticker)
        try:
            t = yf.Ticker(ticker)
            hist = t.history(
                period=period or self._config.history_period, interval="1d"
            )
            if hist is None or hist.empty:
                return empty
            info: dict[str, Any] = t.info or {}
            points: list[CryptoDataPoint] = []
            for idx, row in hist.iterrows():
                points.append(
                    CryptoDataPoint(
                        ticker=ticker,
                        trade_date=_trade_date(idx),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=_nan_safe(row.get("Volume")),
                        market_cap=_nan_safe(info.get("marketCap")),
                    )
                )
            return CryptoDataResponse(ticker=ticker, data=points)
        except Exception:
            logger.exception("get_crypto_data failed for ticker=%s", ticker)
            return empty

    @staticmethod
    def _get_statement_df(
        yt: yf.Ticker, stmt_type: FinancialStatementType, quarterly: bool
    ) -> Any:
        if stmt_type == FinancialStatementType.INCOME_STATEMENT:
            return yt.quarterly_income_stmt if quarterly else yt.income_stmt
        if stmt_type == FinancialStatementType.BALANCE_SHEET:
            return yt.quarterly_balance_sheet if quarterly else yt.balance_sheet
        if stmt_type == FinancialStatementType.CASH_FLOW:
            return yt.quarterly_cashflow if quarterly else yt.cashflow
        return None

    @staticmethod
    def _metric_map_for(
        stmt_type: FinancialStatementType,
    ) -> dict[str, list[str]]:
        if stmt_type == FinancialStatementType.INCOME_STATEMENT:
            return _INCOME_METRICS
        if stmt_type == FinancialStatementType.BALANCE_SHEET:
            return _BALANCE_METRICS
        if stmt_type == FinancialStatementType.CASH_FLOW:
            return _CASHFLOW_METRICS
        return {}

    @staticmethod
    def _parse_recommendations(
        yt: yf.Ticker, ticker: str
    ) -> list[AnalystRecommendation]:
        try:
            ug = yt.upgrades_downgrades
            if ug is None or ug.empty:
                return []
            recs: list[AnalystRecommendation] = []
            for idx, row in ug.iterrows():
                recs.append(
                    AnalystRecommendation(
                        ticker=ticker,
                        firm=row.get("Firm"),
                        rating=row.get("To Grade"),
                        target_price=None,
                        rating_date=_trade_date(idx),
                    )
                )
            return recs
        except Exception:
            logger.exception("_parse_recommendations failed for %s", ticker)
            return []

    @staticmethod
    def _parse_earnings(yt: yf.Ticker, ticker: str) -> list[EarningsEstimate]:
        try:
            eh = yt.earnings_history
            if eh is None or eh.empty:
                return []
            estimates: list[EarningsEstimate] = []
            for idx, row in eh.iterrows():
                period_str = (
                    str(row["period"])
                    if "period" in eh.columns
                    else str(_trade_date(idx))
                )
                estimates.append(
                    EarningsEstimate(
                        ticker=ticker,
                        period=period_str,
                        eps_estimate=_nan_safe(row.get("epsEstimate")),
                        eps_actual=_nan_safe(row.get("epsActual")),
                    )
                )
            return estimates
        except Exception:
            logger.exception("_parse_earnings failed for %s", ticker)
            return []
