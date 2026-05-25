from __future__ import annotations

import logging

from fin_agent.adapters.market_data.akshare.client import AKShareClient
from fin_agent.adapters.market_data.akshare.config import AKShareConfig
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
    ) -> None:
        self._yf = YFinanceClient(yfinance_config)
        self._ak = AKShareClient(akshare_config)

    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        primary, secondary = self._pick(ticker, asset_type)
        resp: MarketDataResponse = primary.get_market_data(
            ticker, asset_type, frequency=frequency, period=period
        )
        if resp.data:
            return resp
        fallback: MarketDataResponse = secondary.get_market_data(
            ticker, asset_type, frequency=frequency, period=period
        )
        return fallback

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        resp_a = self._yf.get_financials(ticker, statement_type, frequency=frequency)
        resp_b = self._ak.get_financials(ticker, statement_type, frequency=frequency)
        merged_data = _merge_records_by_year(resp_a.data, resp_b.data)
        return FinancialStatementResponse(
            ticker=ticker,
            statement_type=statement_type,
            data=merged_data,
        )

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        resp_a = self._yf.get_analyst_data(ticker)
        resp_b = self._ak.get_analyst_data(ticker)
        return _merge_analyst_response(resp_a, resp_b)

    def get_company_info(self, ticker: str) -> CompanyInfo:
        info_a = self._yf.get_company_info(ticker)
        info_b = self._ak.get_company_info(ticker)
        return _merge_company_info(info_a, info_b)

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

    def _pick(
        self, ticker: str, asset_type: AssetType
    ) -> tuple[YFinanceClient | AKShareClient, YFinanceClient | AKShareClient]:
        is_a_share = bool(ticker and ticker[0].isdigit()) and asset_type in (
            AssetType.STOCK,
            AssetType.ETF,
            AssetType.INDEX,
        )
        if is_a_share:
            return self._ak, self._yf
        if asset_type == AssetType.CRYPTO:
            return self._yf, self._ak
        return self._yf, self._ak
