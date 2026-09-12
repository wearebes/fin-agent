from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

import akshare as ak
import pandas as pd
import requests

from fin_agent.adapters.market_data.akshare.config import AKShareConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataPoint,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

# 定义获取时间
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
    "REPORT_DATE": "end_date",
    "TOTAL_OPERATE_INCOME": "total_revenue",
    "NETPROFIT": "net_income",
    "截止日期": "end_date",
    "营业总收入": "total_revenue",
    "净利润": "net_income",
    "营业总收入同比增长率": "revenue_yoy",
    "净利润同比增长率": "net_income_yoy",
    "销售净利率": "net_profit_margin",
}

_BALANCE_COL_MAP: dict[str, str] = {
    "REPORT_DATE": "end_date",
    "TOTAL_ASSETS": "total_assets",
    "TOTAL_LIABILITIES": "total_liabilities",
    "TOTAL_EQUITY": "total_equity",
    "截止日期": "end_date",
    "总资产": "total_assets",
    "总负债": "total_liabilities",
    "所有者权益合计": "total_equity",
}

_CASHFLOW_COL_MAP: dict[str, str] = {
    "REPORT_DATE": "end_date",
    "NETCASH_OPERATE": "operating_cash_flow",
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
        empty = MarketDataResponse(ticker=ticker, asset_type=asset_type, frequency=frequency)
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
        empty = FinancialStatementResponse(ticker=ticker, statement_type=statement_type)
        try:
            symbol = re.sub(r"[^0-9]", "", ticker)
            df = self._fetch_statement(symbol, statement_type)
            if df is None or df.empty:
                return empty

            col_map = self._col_map_for(statement_type)
            df = _map_df_columns(df, col_map)
            df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
            df = df.dropna(subset=["end_date"]).sort_values("end_date", ascending=False)
            if frequency == DataFrequency.YEARLY:
                df = df[df["end_date"].dt.month.eq(12) & df["end_date"].dt.day.eq(31)]
            df = df.drop_duplicates("end_date").head(8)

            records: list[FinancialStatementRecord] = []
            for _, row in df.iterrows():
                end_date = pd.to_datetime(row["end_date"])
                fiscal_year = end_date.year
                fiscal_quarter = (
                    (end_date.month - 1) // 3 + 1 if frequency == DataFrequency.QUARTERLY else None
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
                ticker=ticker,
                statement_type=statement_type,
                data=records,
                source="Eastmoney financial statements (CNY; income/cash flow year-to-date)",
                currency="CNY",
            )
        except Exception:
            logger.exception("get_financials failed for ticker=%s", ticker)
            return empty

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        logger.warning(
            "AKShare analyst data disabled: stock_rank_forecast_cninfo no longer "
            "exposes per-symbol ratings/EPS forecasts. ticker=%s",
            ticker,
        )
        return AnalystResponse(ticker=ticker)

    def get_company_info(self, ticker: str) -> CompanyInfo:
        result = CompanyInfo(ticker=ticker)
        try:
            symbol = re.sub(r"[^0-9]", "", ticker)
            raw = ak.stock_individual_info_em(symbol=symbol, timeout=15)
            info_dict: dict[str, str] = {}
            if raw is not None:
                for _, row in raw.iterrows():
                    info_dict[str(row.iloc[0])] = str(row.iloc[1])
            employees_raw = info_dict.get("员工人数")
            employees = _int_safe(employees_raw) if employees_raw else None
            result = CompanyInfo(
                ticker=ticker,
                name=info_dict.get("公司名称") or info_dict.get("股票简称"),
                sector=info_dict.get("行业"),
                industry=info_dict.get("行业"),
                country=info_dict.get("地区"),
                market_cap=_nan_safe(info_dict.get("总市值")),
                description=info_dict.get("公司简介"),
                employees=employees,
                founded_year=None,
            )
        except Exception:
            logger.exception("get_company_info failed for ticker=%s", ticker)
        if not result.description:
            try:
                response = requests.get(
                    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax",
                    params={"code": _normalize_a_ticker(ticker).upper()},
                    timeout=15,
                )
                response.raise_for_status()
                rows = response.json().get("jbzl") or []
                info = next(
                    row for row in rows if row.get("SECURITY_CODE") == re.sub(r"[^0-9]", "", ticker)
                )
                profile = CompanyInfo(
                    ticker=ticker,
                    name=info.get("ORG_NAME"),
                    industry=info.get("INDUSTRYCSRC1"),
                    description=info.get("ORG_PROFILE"),
                    country="China",
                    employees=_int_safe(info.get("EMP_NUM")),
                )
                return result.model_copy(update=profile.model_dump(exclude_none=True))
            except Exception:
                logger.warning("Company profile fallback unavailable for %s", ticker)
        return result

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
    def _fetch_statement(symbol: str, stmt_type: FinancialStatementType) -> pd.DataFrame | None:
        try:
            symbol = _normalize_a_ticker(symbol).upper()
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
