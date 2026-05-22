from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

import akshare as ak
import pandas as pd

from fin_agent.adapters.market_data.akshare.config import AKShareConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystRecommendation,
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    EarningsEstimate,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataPoint,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

_PERIOD_DAYS: dict[str, int] = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "2y": 730,
    "3y": 1095,
    "5y": 1825,
}

_FREQUENCY_PERIOD: dict[DataFrequency, str] = {
    DataFrequency.DAILY: "daily",
    DataFrequency.WEEKLY: "weekly",
    DataFrequency.MONTHLY: "monthly",
}

_ADJUST_MAP: dict[str, str] = {
    "qfq": "qfq",
    "hfq": "hfq",
    "": "",
}

_HIST_COL_MAP: dict[str, str] = {
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "turnover",
    "换手率": "turnover_rate",
    "涨跌幅": "pct_change",
}

_INCOME_COL_MAP: dict[str, str] = {
    "截止日期": "end_date",
    "营业总收入": "total_revenue",
    "净利润": "net_income",
    "营业总收入同比增长率": "revenue_yoy",
    "净利润同比增长率": "net_income_yoy",
    "销售净利率": "net_profit_margin",
}

_BALANCE_COL_MAP: dict[str, str] = {
    "截止日期": "end_date",
    "总资产": "total_assets",
    "总负债": "total_liabilities",
    "所有者权益合计": "total_equity",
}

_CASHFLOW_COL_MAP: dict[str, str] = {
    "截止日期": "end_date",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "自由现金流量": "free_cash_flow",
}

_INFO_COL_MAP: dict[str, str] = {
    "公司名称": "name",
    "行业": "industry",
    "地区": "country",
    "公司简介": "description",
    "员工人数": "employees",
    "上市时间": "list_date",
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


def _period_to_start(period: str) -> str:
    days = _PERIOD_DAYS.get(period, 365)
    start = date.today() - timedelta(days=days)
    return start.strftime("%Y%m%d")


def _normalize_a_ticker(ticker: str) -> str:
    cleaned = re.sub(r"[^0-9]", "", ticker)
    if not cleaned:
        return ticker
    if cleaned.startswith("6") or cleaned.startswith("9"):
        return f"sh{cleaned}"
    if cleaned.startswith("0") or cleaned.startswith("3") or cleaned.startswith("2"):
        return f"sz{cleaned}"
    if cleaned.startswith("4") or cleaned.startswith("8"):
        return f"bj{cleaned}"
    return cleaned


def _map_df_columns(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for cn, en in col_map.items():
        if cn in df.columns:
            rename[cn] = en
    return df.rename(columns=rename)


class AKShareClient:
    def __init__(self, config: AKShareConfig | None = None) -> None:
        self._config = config or AKShareConfig()

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
            start_date = _period_to_start(period or self._config.history_period)
            end_date = date.today().strftime("%Y%m%d")
            period_str = _FREQUENCY_PERIOD.get(frequency, "daily")
            symbol = _normalize_a_ticker(ticker)

            if asset_type == AssetType.INDEX:
                raw = ak.stock_zh_index_daily_em(symbol=symbol)
            else:
                raw = ak.stock_zh_a_hist(
                    symbol=re.sub(r"[a-zA-Z]", "", ticker),
                    period=period_str,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=self._config.adjust,
                )

            if raw is None or raw.empty:
                return empty

            df = _map_df_columns(raw, _HIST_COL_MAP)
            points: list[MarketDataPoint] = []
            for _, row in df.iterrows():
                trade_date = pd.to_datetime(row["trade_date"]).date()
                points.append(
                    MarketDataPoint(
                        ticker=ticker,
                        asset_type=asset_type,
                        trade_date=trade_date,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=_int_safe(row.get("volume")),
                        turnover=_nan_safe(row.get("turnover")),
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
            symbol = re.sub(r"[a-zA-Z]", "", ticker)
            df = self._fetch_statement(symbol, statement_type)
            if df is None or df.empty:
                return empty

            col_map = self._col_map_for(statement_type)
            df = _map_df_columns(df, col_map)

            records: list[FinancialStatementRecord] = []
            for _, row in df.iterrows():
                end_date = pd.to_datetime(row["end_date"])
                fiscal_year = end_date.year
                fiscal_quarter = (
                    (end_date.month - 1) // 3 + 1
                    if frequency == DataFrequency.QUARTERLY
                    else None
                )
                records.append(
                    FinancialStatementRecord(
                        ticker=ticker,
                        statement_type=statement_type,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        total_revenue=_nan_safe(row.get("total_revenue")),
                        net_income=_nan_safe(row.get("net_income")),
                        total_assets=_nan_safe(row.get("total_assets")),
                        total_liabilities=_nan_safe(row.get("total_liabilities")),
                        total_equity=_nan_safe(row.get("total_equity")),
                        operating_cash_flow=_nan_safe(row.get("operating_cash_flow")),
                        free_cash_flow=_nan_safe(row.get("free_cash_flow")),
                        revenue_yoy=_nan_safe(row.get("revenue_yoy")),
                        net_profit_margin=_nan_safe(row.get("net_profit_margin")),
                    )
                )
            return FinancialStatementResponse(
                ticker=ticker, statement_type=statement_type, data=records
            )
        except Exception:
            logger.exception("get_financials failed for ticker=%s", ticker)
            return empty

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        empty = AnalystResponse(ticker=ticker)
        try:
            symbol = re.sub(r"[a-zA-Z]", "", ticker)
            recs = self._parse_recommendations(symbol, ticker)
            estimates = self._parse_earnings(symbol, ticker)
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
            symbol = re.sub(r"[a-zA-Z]", "", ticker)
            raw = ak.stock_individual_info_em(symbol=symbol)
            if raw is None or raw.empty:
                return CompanyInfo(ticker=ticker)
            info_dict: dict[str, str] = {}
            for _, row in raw.iterrows():
                info_dict[str(row.iloc[0])] = str(row.iloc[1])
            employees_raw = info_dict.get("员工人数")
            employees = _int_safe(employees_raw) if employees_raw else None
            return CompanyInfo(
                ticker=ticker,
                name=info_dict.get("公司名称"),
                sector=info_dict.get("行业"),
                industry=info_dict.get("行业"),
                country=info_dict.get("地区"),
                market_cap=None,
                description=info_dict.get("公司简介"),
                employees=employees,
                founded_year=None,
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
        logger.warning(
            "AKShare does not support historical crypto data; "
            "use the yfinance adapter for crypto. ticker=%s",
            ticker,
        )
        return CryptoDataResponse(ticker=ticker)

    @staticmethod
    def _fetch_statement(
        symbol: str, stmt_type: FinancialStatementType
    ) -> pd.DataFrame | None:
        try:
            if stmt_type == FinancialStatementType.INCOME_STATEMENT:
                return ak.stock_profit_sheet_by_report_em(symbol=symbol)
            if stmt_type == FinancialStatementType.BALANCE_SHEET:
                return ak.stock_balance_sheet_by_report_em(symbol=symbol)
            if stmt_type == FinancialStatementType.CASH_FLOW:
                return ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
        except Exception:
            logger.exception("_fetch_statement failed for %s", symbol)
        return None

    @staticmethod
    def _col_map_for(
        stmt_type: FinancialStatementType,
    ) -> dict[str, str]:
        if stmt_type == FinancialStatementType.INCOME_STATEMENT:
            return _INCOME_COL_MAP
        if stmt_type == FinancialStatementType.BALANCE_SHEET:
            return _BALANCE_COL_MAP
        if stmt_type == FinancialStatementType.CASH_FLOW:
            return _CASHFLOW_COL_MAP
        return {}

    @staticmethod
    def _parse_recommendations(
        symbol: str, ticker: str
    ) -> list[AnalystRecommendation]:
        try:
            raw = ak.stock_rank_forecast_cninfo(symbol=symbol)
            if raw is None or raw.empty:
                return []
            recs: list[AnalystRecommendation] = []
            for _, row in raw.iterrows():
                rating_date = None
                if "日期" in raw.columns:
                    rating_date = pd.to_datetime(row["日期"]).date()
                recs.append(
                    AnalystRecommendation(
                        ticker=ticker,
                        firm=str(row.get("机构名称", "")) or None,
                        rating=str(row.get("评级", "")) or None,
                        target_price=_nan_safe(row.get("目标价格")),
                        rating_date=rating_date,
                    )
                )
            return recs
        except Exception:
            logger.exception("_parse_recommendations failed for %s", ticker)
            return []

    @staticmethod
    def _parse_earnings(
        symbol: str, ticker: str
    ) -> list[EarningsEstimate]:
        try:
            raw = ak.stock_rank_forecast_cninfo(symbol=symbol)
            if raw is None or raw.empty:
                return []
            estimates: list[EarningsEstimate] = []
            for _, row in raw.iterrows():
                period_str = str(row.get("预测年份", ""))
                estimates.append(
                    EarningsEstimate(
                        ticker=ticker,
                        period=period_str,
                        eps_estimate=_nan_safe(row.get("预测EPS")),
                        eps_actual=None,
                    )
                )
            return estimates
        except Exception:
            logger.exception("_parse_earnings failed for %s", ticker)
            return []
