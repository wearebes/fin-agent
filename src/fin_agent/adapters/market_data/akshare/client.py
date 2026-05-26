from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.request
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

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_DC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
}


def _dc_fetch(url: str, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_DC_HEADERS)
    r = urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)
    return json.loads(r.read().decode())

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
        points = self._ak_market_data(ticker, asset_type, frequency, period)
        if not points:
            points = self._dc_market_data(ticker, asset_type, period)
        if not points:
            return empty
        return MarketDataResponse(
            ticker=ticker, asset_type=asset_type, frequency=frequency, data=points
        )

    def _ak_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        frequency: DataFrequency,
        period: str | None,
    ) -> list[MarketDataPoint]:
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
                return []

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
            return points
        except Exception:
            logger.debug("AKShare market_data failed for %s, will try datacenter fallback", ticker)
            return []

    def _dc_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        period: str | None,
    ) -> list[MarketDataPoint]:
        try:
            digits = re.sub(r"[^0-9]", "", ticker)
            if not digits:
                return []
            if digits.startswith("6") or digits.startswith("9"):
                secid = f"1.{digits}"
            else:
                secid = f"0.{digits}"
            start_date = _period_to_start(period or self._config.history_period)
            end_date = date.today().strftime("%Y%m%d")
            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
                f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
                f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                f"&klt=101&fqt=1&beg={start_date}&end={end_date}"
            )
            data = _dc_fetch(url)
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return []
            points: list[MarketDataPoint] = []
            for line in klines:
                parts = line.split(",")
                if len(parts) < 7:
                    continue
                points.append(
                    MarketDataPoint(
                        ticker=ticker,
                        asset_type=asset_type,
                        trade_date=date.fromisoformat(parts[0]),
                        open=float(parts[1]),
                        close=float(parts[2]),
                        high=float(parts[3]),
                        low=float(parts[4]),
                        volume=_int_safe(parts[5]),
                        turnover=_nan_safe(parts[6]),
                    )
                )
            return points
        except Exception:
            logger.debug("datacenter market_data fallback also failed for %s", ticker)
            return []

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
        records = self._ak_financials(ticker, statement_type, frequency)
        if not records:
            records = self._dc_financials(ticker, statement_type, frequency)
        if not records:
            return empty
        return FinancialStatementResponse(
            ticker=ticker, statement_type=statement_type, data=records
        )

    def _ak_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        frequency: DataFrequency,
    ) -> list[FinancialStatementRecord]:
        try:
            symbol = re.sub(r"[a-zA-Z]", "", ticker)
            df = self._fetch_statement(symbol, statement_type)
            if df is None or df.empty:
                return []

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
            return records
        except Exception:
            logger.debug("AKShare financials failed for %s, will try datacenter fallback", ticker)
            return []

    _DC_STMT_REPORT: dict[FinancialStatementType, str] = {
        FinancialStatementType.BALANCE_SHEET: "RPT_DMSK_FN_BALANCE",
        FinancialStatementType.INCOME_STATEMENT: "RPT_DMSK_FN_INCOME",
        FinancialStatementType.CASH_FLOW: "RPT_DMSK_FN_CASHFLOW",
    }

    _DC_STMT_COLS: dict[FinancialStatementType, str] = {
        FinancialStatementType.BALANCE_SHEET: "SECURITY_CODE,REPORT_DATE,TOTAL_ASSETS,TOTAL_LIABILITIES,TOTAL_EQUITY,DEBT_ASSET_RATIO",
        FinancialStatementType.INCOME_STATEMENT: "SECURITY_CODE,REPORT_DATE,TOTAL_OPERATE_INCOME,TOE_RATIO,PARENT_NETPROFIT,PARENT_NETPROFIT_RATIO,OPERATE_PROFIT,OPERATE_PROFIT_RATIO",
        FinancialStatementType.CASH_FLOW: "SECURITY_CODE,REPORT_DATE,NETCASH_OPERATE,FREE_CASHFLOW",
    }

    def _dc_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        frequency: DataFrequency,
    ) -> list[FinancialStatementRecord]:
        try:
            digits = re.sub(r"[^0-9]", "", ticker)
            if not digits:
                return []
            report_name = self._DC_STMT_REPORT.get(statement_type)
            columns = self._DC_STMT_COLS.get(statement_type)
            if not report_name or not columns:
                return []
            url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get"
                f"?reportName={report_name}"
                f"&columns={columns}"
                f"&filter=(SECURITY_CODE=%22{digits}%22)"
                "&pageSize=4&sortColumns=REPORT_DATE&sortTypes=-1"
            )
            data = _dc_fetch(url)
            items = (data.get("result") or {}).get("data") or []
            if not items:
                return []
            records: list[FinancialStatementRecord] = []
            for item in items:
                report_date_str = (item.get("REPORT_DATE") or "")[:10]
                if not report_date_str:
                    continue
                from datetime import datetime as _dt
                rd = _dt.strptime(report_date_str, "%Y-%m-%d")
                fiscal_quarter = (rd.month - 1) // 3 + 1 if frequency == DataFrequency.QUARTERLY else None
                total_assets = _nan_safe(item.get("TOTAL_ASSETS"))
                total_liabilities = _nan_safe(item.get("TOTAL_LIABILITIES"))
                total_equity = _nan_safe(item.get("TOTAL_EQUITY"))
                total_revenue = _nan_safe(item.get("TOTAL_OPERATE_INCOME"))
                net_income = _nan_safe(item.get("PARENT_NETPROFIT"))
                operating_cf = _nan_safe(item.get("NETCASH_OPERATE"))
                free_cf = _nan_safe(item.get("FREE_CASHFLOW"))
                revenue_yoy = _nan_safe(item.get("TOE_RATIO"))
                net_margin = _nan_safe(item.get("PARENT_NETPROFIT_RATIO"))
                records.append(
                    FinancialStatementRecord(
                        ticker=ticker,
                        statement_type=statement_type,
                        fiscal_year=rd.year,
                        fiscal_quarter=fiscal_quarter,
                        total_assets=total_assets,
                        total_liabilities=total_liabilities,
                        total_equity=total_equity,
                        total_revenue=total_revenue,
                        net_income=net_income,
                        operating_cash_flow=operating_cf,
                        free_cash_flow=free_cf,
                        revenue_yoy=revenue_yoy,
                        net_profit_margin=net_margin,
                    )
                )
            return records
        except Exception:
            logger.debug("datacenter financials fallback also failed for %s", ticker)
            return []

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
        info = self._ak_company_info(ticker)
        if info.name:
            return info
        fallback = self._dc_company_info(ticker)
        if fallback.name:
            return fallback
        return info

    def _ak_company_info(self, ticker: str) -> CompanyInfo:
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
            logger.debug("AKShare company_info failed for %s, will try datacenter fallback", ticker)
            return CompanyInfo(ticker=ticker)

    def _dc_company_info(self, ticker: str) -> CompanyInfo:
        try:
            digits = re.sub(r"[^0-9]", "", ticker)
            if not digits:
                return CompanyInfo(ticker=ticker)
            url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get"
                "?reportName=RPT_DMSK_FN_INCOME"
                "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,INDUSTRY_NAME"
                f"&filter=(SECURITY_CODE=%22{digits}%22)"
                "&pageSize=1&sortColumns=REPORT_DATE&sortTypes=-1"
            )
            data = _dc_fetch(url)
            items = (data.get("result") or {}).get("data") or []
            if not items:
                return CompanyInfo(ticker=ticker)
            item = items[0]
            name = item.get("SECURITY_NAME_ABBR") or None
            industry = item.get("INDUSTRY_NAME") or None
            url2 = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get"
                "?reportName=RPT_F10_BASIC_ORGINFO"
                "&columns=SECURITY_CODE,ORG_PROFILE"
                f"&filter=(SECURITY_CODE=%22{digits}%22)"
                "&pageSize=1"
            )
            desc = None
            try:
                data2 = _dc_fetch(url2)
                items2 = (data2.get("result") or {}).get("data") or []
                if items2:
                    profile = items2[0].get("ORG_PROFILE", "")
                    desc = profile.strip() if profile else None
            except Exception:
                pass
            return CompanyInfo(
                ticker=ticker,
                name=name,
                sector=industry,
                industry=industry,
                description=desc,
            )
        except Exception:
            logger.debug("datacenter company_info fallback also failed for %s", ticker)
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
