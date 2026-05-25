from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.domain.constants import (
    AssetType,
    DataFrequency,
    FinancialStatementType,
)
from fin_agent.domain.types import (
    AnalystRecommendation,
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementRecord,
    FinancialStatementResponse,
    MarketDataPoint,
    MarketDataResponse,
)


def _market_resp(ticker: str, source: str) -> MarketDataResponse:
    return MarketDataResponse(
        ticker=ticker,
        asset_type=AssetType.STOCK,
        frequency=DataFrequency.DAILY,
        data=[
            MarketDataPoint(
                ticker=ticker,
                asset_type=AssetType.STOCK,
                trade_date=date(2025, 1, 2),
                open=100.0 if source == "yf" else 99.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1000000,
            )
        ],
    )


def _empty_market_resp(ticker: str) -> MarketDataResponse:
    return MarketDataResponse(
        ticker=ticker, asset_type=AssetType.STOCK, frequency=DataFrequency.DAILY
    )


def _financial_resp(
    ticker: str,
    revenue: float | None,
    net_income: float | None,
) -> FinancialStatementResponse:
    return FinancialStatementResponse(
        ticker=ticker,
        statement_type=FinancialStatementType.INCOME_STATEMENT,
        data=[
            FinancialStatementRecord(
                ticker=ticker,
                statement_type=FinancialStatementType.INCOME_STATEMENT,
                fiscal_year=2024,
                total_revenue=revenue,
                net_income=net_income,
            )
        ],
    )


def _analyst_resp(ticker: str, firms: list[str]) -> AnalystResponse:
    return AnalystResponse(
        ticker=ticker,
        recommendations=[
            AnalystRecommendation(ticker=ticker, firm=f, rating="Buy")
            for f in firms
        ],
    )


def _company_info(ticker: str, name: str | None, sector: str | None) -> CompanyInfo:
    return CompanyInfo(ticker=ticker, name=name, sector=sector)


class TestGetMarketDataRouting:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_a_stock_uses_akshare_primary(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        ak_instance.get_market_data.return_value = _market_resp("600519", "ak")

        router = MarketDataRouter()
        router.get_market_data("600519", AssetType.STOCK)

        ak_instance.get_market_data.assert_called_once()
        yf_instance.get_market_data.assert_not_called()

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_us_stock_uses_yfinance_primary(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        yf_instance.get_market_data.return_value = _market_resp("AAPL", "yf")

        router = MarketDataRouter()
        router.get_market_data("AAPL", AssetType.STOCK)

        yf_instance.get_market_data.assert_called_once()
        ak_instance.get_market_data.assert_not_called()

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_fallback_to_secondary_when_primary_empty(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        ak_instance.get_market_data.return_value = _empty_market_resp("600519")
        yf_instance.get_market_data.return_value = _market_resp("600519", "yf")

        router = MarketDataRouter()
        resp = router.get_market_data("600519", AssetType.STOCK)

        assert len(resp.data) == 1
        yf_instance.get_market_data.assert_called_once()


class TestGetFinancialsFusion:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_merges_records_from_both_sources(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_financials.return_value = _financial_resp("AAPL", 500000.0, None)
        ak_instance.get_financials.return_value = _financial_resp("AAPL", None, 100000.0)

        router = MarketDataRouter()
        resp = router.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        assert len(resp.data) == 1
        assert resp.data[0].total_revenue == 500000.0
        assert resp.data[0].net_income == 100000.0

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_deduplicates_by_year(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_financials.return_value = _financial_resp("AAPL", 500000.0, None)
        ak_instance.get_financials.return_value = _financial_resp("AAPL", 480000.0, 100000.0)

        router = MarketDataRouter()
        resp = router.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        assert len(resp.data) == 1
        assert resp.data[0].total_revenue == 500000.0
        assert resp.data[0].net_income == 100000.0


class TestGetAnalystDataFusion:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_merges_recommendations_dedup_by_firm(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_analyst_data.return_value = _analyst_resp("AAPL", ["Goldman", "Morgan"])
        ak_instance.get_analyst_data.return_value = _analyst_resp("AAPL", ["Morgan", "中信证券"])

        router = MarketDataRouter()
        resp = router.get_analyst_data("AAPL")

        firms = [r.firm for r in resp.recommendations]
        assert "Goldman" in firms
        assert "Morgan" in firms
        assert "中信证券" in firms
        assert len(resp.recommendations) == 3


class TestGetCompanyInfoFusion:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_fills_gaps_from_secondary(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_company_info.return_value = _company_info("AAPL", "Apple Inc.", None)
        ak_instance.get_company_info.return_value = _company_info("AAPL", None, "Technology")

        router = MarketDataRouter()
        info = router.get_company_info("AAPL")

        assert info.name == "Apple Inc."
        assert info.sector == "Technology"


class TestGetCryptoDataRouting:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_crypto_uses_yfinance_primary(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        yf_instance.get_crypto_data.return_value = CryptoDataResponse(
            ticker="BTC-USD", data=[]
        )

        router = MarketDataRouter()
        router.get_crypto_data("BTC-USD")

        yf_instance.get_crypto_data.assert_called_once()
