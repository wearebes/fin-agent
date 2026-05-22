"""Market data adapters."""

from __future__ import annotations

from typing import Protocol

from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementResponse,
    MarketDataResponse,
)

__all__ = ["MarketDataProvider", "MarketDataRouter"]


class MarketDataProvider(Protocol):
    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse: ...

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse: ...

    def get_analyst_data(self, ticker: str) -> AnalystResponse: ...

    def get_company_info(self, ticker: str) -> CompanyInfo: ...

    def get_crypto_data(
        self,
        ticker: str,
        *,
        period: str | None = None,
    ) -> CryptoDataResponse: ...
