from __future__ import annotations

import logging
import re

from fin_agent.adapters.market_data.akshare.client import AKShareClient
from fin_agent.adapters.market_data.akshare.config import AKShareConfig
from fin_agent.adapters.market_data.fmp.client import FMPClient
from fin_agent.adapters.market_data.fmp.config import FMPConfig
from fin_agent.adapters.market_data.yfinance.client import YFinanceClient
from fin_agent.adapters.market_data.yfinance.config import YFinanceConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

_A_SHARE_RE = re.compile(r"^(sh|sz|bj)?\d{6}$", re.IGNORECASE)


def _is_a_share_ticker(ticker: str) -> bool:
    """纯 6 位大陆代码，或带 sh/sz/bj 前缀的 6 位代码。

    AAPL / 0700.HK / BTC-USD 均为 False。用于决定是否调用 AKShare
    （中国市场数据源），避免非 A 股 ticker 触发无效的中国接口调用。
    """
    return bool(ticker) and bool(_A_SHARE_RE.match(ticker.strip()))


def _first_non_none[T](*values: T | None) -> T | None:
    for v in values:
        if v is not None:
            return v
    return None


def _merge_company_info(a: CompanyInfo, b: CompanyInfo) -> CompanyInfo:
    return CompanyInfo(
        ticker=a.ticker or b.ticker,
        name=_first_non_none(a.name, b.name),
        sector=_first_non_none(a.sector, b.sector),
        industry=_first_non_none(a.industry, b.industry),
        country=_first_non_none(a.country, b.country),
        market_cap=_first_non_none(a.market_cap, b.market_cap),
        description=_first_non_none(a.description, b.description),
        employees=_first_non_none(a.employees, b.employees),
        founded_year=_first_non_none(a.founded_year, b.founded_year),
    )


def _merge_analyst_response(a: AnalystResponse, b: AnalystResponse) -> AnalystResponse:
    seen_firms = {r.firm for r in a.recommendations if r.firm}
    extra_recs = [r for r in b.recommendations if r.firm not in seen_firms]
    seen_periods = {e.period for e in a.earnings_estimates}
    extra_est = [e for e in b.earnings_estimates if e.period not in seen_periods]
    return AnalystResponse(
        ticker=a.ticker,
        recommendations=a.recommendations + extra_recs,
        earnings_estimates=a.earnings_estimates + extra_est,
    )


def _merge_records_by_year(
    a: list[FinancialStatementRecord], b: list[FinancialStatementRecord]
) -> list[FinancialStatementRecord]:
    b_map: dict[tuple[int, int | None], FinancialStatementRecord] = {}
    for r in b:
        key = (r.fiscal_year, r.fiscal_quarter)
        b_map[key] = r
    merged: list[FinancialStatementRecord] = []
    for r in a:
        key = (r.fiscal_year, r.fiscal_quarter)
        other = b_map.pop(key, None)
        if other is None:
            merged.append(r)
            continue
        merged.append(
            FinancialStatementRecord(
                ticker=r.ticker,
                statement_type=r.statement_type,
                fiscal_year=r.fiscal_year,
                fiscal_quarter=_first_non_none(
                    r.fiscal_quarter, other.fiscal_quarter
                ),
                revenue_yoy=_first_non_none(r.revenue_yoy, other.revenue_yoy),
                net_profit_margin=_first_non_none(
                    r.net_profit_margin, other.net_profit_margin
                ),
                premium_income=_first_non_none(
                    r.premium_income, other.premium_income
                ),
                inventory_turnover_days=_first_non_none(
                    r.inventory_turnover_days, other.inventory_turnover_days
                ),
                total_revenue=_first_non_none(
                    r.total_revenue, other.total_revenue
                ),
                net_income=_first_non_none(r.net_income, other.net_income),
                total_assets=_first_non_none(
                    r.total_assets, other.total_assets
                ),
                total_liabilities=_first_non_none(
                    r.total_liabilities, other.total_liabilities
                ),
                total_equity=_first_non_none(
                    r.total_equity, other.total_equity
                ),
                operating_cash_flow=_first_non_none(
                    r.operating_cash_flow, other.operating_cash_flow
                ),
                free_cash_flow=_first_non_none(
                    r.free_cash_flow, other.free_cash_flow
                ),
                net_operating_cash_flow=_first_non_none(
                    r.net_operating_cash_flow, other.net_operating_cash_flow
                ),
                solvency_adequacy_ratio=_first_non_none(
                    r.solvency_adequacy_ratio, other.solvency_adequacy_ratio
                ),
            )
        )
    for r in b_map.values():
        merged.append(r)
    return merged


class MarketDataRouter:
    def __init__(
        self,
        yfinance_config: YFinanceConfig | None = None,
        akshare_config: AKShareConfig | None = None,
        fmp_config: FMPConfig | None = None,
    ) -> None:
        self._yf = YFinanceClient(yfinance_config)
        self._ak = AKShareClient(akshare_config)
        self._fmp = FMPClient(fmp_config)

    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        is_a_share = _is_a_share_ticker(ticker) and asset_type in (
            AssetType.STOCK, AssetType.ETF, AssetType.INDEX,
        )
        if is_a_share:
            resp = self._ak.get_market_data(ticker, asset_type, frequency=frequency, period=period)
            if resp.data:
                return resp
        if self._fmp._api_key:
            resp = self._fmp.get_market_data(ticker, asset_type, frequency=frequency, period=period)
            if resp.data:
                return resp
        resp = self._yf.get_market_data(ticker, asset_type, frequency=frequency, period=period)
        if resp.data:
            return resp
        return MarketDataResponse(ticker=ticker, asset_type=asset_type, frequency=frequency)

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        resp_a = self._yf.get_financials(ticker, statement_type, frequency=frequency)
        merged_data = resp_a.data
        if _is_a_share_ticker(ticker):
            resp_b = self._ak.get_financials(ticker, statement_type, frequency=frequency)
            merged_data = _merge_records_by_year(merged_data, resp_b.data)
        if self._fmp._api_key:
            resp_c = self._fmp.get_financials(ticker, statement_type, frequency=frequency)
            merged_data = _merge_records_by_year(merged_data, resp_c.data)
        return FinancialStatementResponse(
            ticker=ticker,
            statement_type=statement_type,
            data=merged_data,
        )

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        # AKShare analyst data is disabled (stock_rank_forecast_cninfo no longer
        # exposes per-symbol ratings/EPS forecasts), so analyst data comes from
        # yfinance (and optionally FMP) for both A-share and non-A-share tickers.
        merged = self._yf.get_analyst_data(ticker)
        if self._fmp._api_key:
            fmp_recs = self._fmp.get_analyst_data(ticker)
            if fmp_recs:
                extra = AnalystResponse(ticker=ticker, recommendations=fmp_recs)
                merged = _merge_analyst_response(merged, extra)
        return merged

    def get_company_info(self, ticker: str) -> CompanyInfo:
        merged = self._yf.get_company_info(ticker)
        if _is_a_share_ticker(ticker):
            info_b = self._ak.get_company_info(ticker)
            merged = _merge_company_info(merged, info_b)
        if self._fmp._api_key:
            info_c = self._fmp.get_company_info(ticker)
            if info_c:
                merged = _merge_company_info(merged, info_c)
        return merged

    def get_crypto_data(
        self,
        ticker: str,
        *,
        period: str | None = None,
    ) -> CryptoDataResponse:
        resp: CryptoDataResponse = self._yf.get_crypto_data(ticker, period=period)
        if resp.data:
            return resp
        fallback: CryptoDataResponse = self._ak.get_crypto_data(
            ticker, period=period
        )
        return fallback


