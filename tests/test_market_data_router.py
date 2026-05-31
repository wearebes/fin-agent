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

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_non_a_share_does_not_fall_back_to_akshare(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        yf_instance.get_market_data.return_value = _empty_market_resp("AAPL")

        router = MarketDataRouter()
        resp = router.get_market_data("AAPL", AssetType.STOCK)

        ak_instance.get_market_data.assert_not_called()
        assert len(resp.data) == 0


class TestGetFinancialsFusion:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_merges_records_from_both_sources(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_financials.return_value = _financial_resp("600519", 500000.0, None)
        ak_instance.get_financials.return_value = _financial_resp("600519", None, 100000.0)

        router = MarketDataRouter()
        resp = router.get_financials("600519", FinancialStatementType.INCOME_STATEMENT)

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

        yf_instance.get_financials.return_value = _financial_resp("600519", 500000.0, None)
        ak_instance.get_financials.return_value = _financial_resp("600519", 480000.0, 100000.0)

        router = MarketDataRouter()
        resp = router.get_financials("600519", FinancialStatementType.INCOME_STATEMENT)

        assert len(resp.data) == 1
        assert resp.data[0].total_revenue == 500000.0
        assert resp.data[0].net_income == 100000.0

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_non_a_share_skips_akshare(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_financials.return_value = _financial_resp("AAPL", 500000.0, 90000.0)

        router = MarketDataRouter()
        resp = router.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        ak_instance.get_financials.assert_not_called()
        assert len(resp.data) == 1
        assert resp.data[0].total_revenue == 500000.0


class TestGetAnalystDataRouting:
    """AKShare analyst data is disabled, so router never calls _ak here —
    analyst data comes from yfinance (and optionally FMP) for all tickers."""

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_a_share_skips_akshare(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_analyst_data.return_value = _analyst_resp("600519", ["Goldman", "Morgan"])

        router = MarketDataRouter()
        resp = router.get_analyst_data("600519")

        ak_instance.get_analyst_data.assert_not_called()
        assert len(resp.recommendations) == 2

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_non_a_share_skips_akshare(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_analyst_data.return_value = _analyst_resp("AAPL", ["Goldman", "Morgan"])

        router = MarketDataRouter()
        resp = router.get_analyst_data("AAPL")

        ak_instance.get_analyst_data.assert_not_called()
        assert len(resp.recommendations) == 2


class TestGetCompanyInfoFusion:
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_fills_gaps_from_secondary(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_company_info.return_value = _company_info("600519", "贵州茅台", None)
        ak_instance.get_company_info.return_value = _company_info("600519", None, "白酒")

        router = MarketDataRouter()
        info = router.get_company_info("600519")

        assert info.name == "贵州茅台"
        assert info.sector == "白酒"

    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_non_a_share_skips_akshare(self, MockAK, MockYF):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance

        yf_instance.get_company_info.return_value = _company_info("AAPL", "Apple Inc.", "Technology")

        router = MarketDataRouter()
        info = router.get_company_info("AAPL")

        ak_instance.get_company_info.assert_not_called()
        assert info.name == "Apple Inc."
        assert info.sector == "Technology"


class TestFMPFusion:
    @patch("fin_agent.adapters.market_data.router.FMPClient")
    @patch("fin_agent.adapters.market_data.router.YFinanceClient")
    @patch("fin_agent.adapters.market_data.router.AKShareClient")
    def test_financials_merges_fmp_when_key_present(self, MockAK, MockYF, MockFMP):
        ak_instance = MagicMock()
        yf_instance = MagicMock()
        fmp_instance = MagicMock()
        MockAK.return_value = ak_instance
        MockYF.return_value = yf_instance
        MockFMP.return_value = fmp_instance
        fmp_instance._api_key = "x"

        yf_instance.get_financials.return_value = _financial_resp("AAPL", 500000.0, None)
        fmp_instance.get_financials.return_value = _financial_resp("AAPL", None, 100000.0)

        router = MarketDataRouter()
        resp = router.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        ak_instance.get_financials.assert_not_called()
        fmp_instance.get_financials.assert_called_once()
        # Reads resp_c.data (not the non-existent .records) and merges by year.
        assert len(resp.data) == 1
        assert resp.data[0].total_revenue == 500000.0
        assert resp.data[0].net_income == 100000.0


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
