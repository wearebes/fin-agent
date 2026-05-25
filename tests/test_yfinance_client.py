from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fin_agent.adapters.market_data.yfinance import YFinanceClient, YFinanceConfig
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
    EarningsEstimate,
    FinancialStatementResponse,
    MarketDataResponse,
)


def _make_history_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.5],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.5],
            "Close": [101.0, 102.5],
            "Volume": [1000000, 1200000],
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03")]
        ),
    )


def _make_income_stmt_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [500000.0, 100000.0],
            pd.Timestamp("2023-12-31"): [400000.0, 80000.0],
        },
        index=["Total Revenue", "Net Income"],
    )


def _make_balance_sheet_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [1000000.0, 400000.0, 600000.0],
        },
        index=["Total Assets", "Total Liabilities", "Stockholders Equity"],
    )


def _make_cashflow_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            pd.Timestamp("2024-12-31"): [150000.0, 80000.0],
        },
        index=["Operating Cash Flow", "Free Cash Flow"],
    )


def _make_upgrades_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Firm": ["Goldman", "Morgan"],
            "To Grade": ["Buy", "Hold"],
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp("2025-01-10"), pd.Timestamp("2025-01-12")]
        ),
    )


def _make_earnings_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period": ["2025Q1", "2024Q4"],
            "epsEstimate": [1.5, 1.2],
            "epsActual": [1.6, 1.1],
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp("2025-01-15"), pd.Timestamp("2024-12-15")]
        ),
    )


def _mock_ticker(
    history_df: pd.DataFrame | None = None,
    info: dict | None = None,
    income_stmt: pd.DataFrame | None = None,
    balance_sheet: pd.DataFrame | None = None,
    cashflow: pd.DataFrame | None = None,
    upgrades: pd.DataFrame | None = None,
    earnings: pd.DataFrame | None = None,
    *,
    use_default_info: bool = True,
) -> MagicMock:
    if history_df is None:
        history_df = _make_history_df()
    t = MagicMock()
    t.history.return_value = history_df
    _default_info = {
        "longName": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
        "country": "US",
        "marketCap": 1e12,
        "longBusinessSummary": "A test company.",
        "fullTimeEmployees": 50000,
        "foundedYear": 2000,
    }
    t.info = info if info is not None else (_default_info if use_default_info else {})
    t.income_stmt = income_stmt
    t.quarterly_income_stmt = income_stmt
    t.balance_sheet = balance_sheet
    t.quarterly_balance_sheet = balance_sheet
    t.cashflow = cashflow
    t.quarterly_cashflow = cashflow
    t.upgrades_downgrades = upgrades
    t.earnings_history = earnings
    return t


class TestGetMarketData:
    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_converts_dataframe_to_market_data_response(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker()
        client = YFinanceClient()
        resp = client.get_market_data("AAPL", AssetType.STOCK)

        assert isinstance(resp, MarketDataResponse)
        assert resp.ticker == "AAPL"
        assert resp.asset_type == AssetType.STOCK
        assert resp.frequency == DataFrequency.DAILY
        assert len(resp.data) == 2
        p = resp.data[0]
        assert p.ticker == "AAPL"
        assert p.trade_date == date(2025, 1, 2)
        assert p.open == 100.0
        assert p.high == 102.0
        assert p.low == 99.0
        assert p.close == 101.0
        assert p.volume == 1000000

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_empty_history_returns_empty_response(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(history_df=pd.DataFrame())
        client = YFinanceClient()
        resp = client.get_market_data("AAPL", AssetType.STOCK)

        assert isinstance(resp, MarketDataResponse)
        assert len(resp.data) == 0

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_exception_returns_empty_response(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network error")
        client = YFinanceClient()
        resp = client.get_market_data("AAPL", AssetType.STOCK)

        assert isinstance(resp, MarketDataResponse)
        assert len(resp.data) == 0
        assert resp.ticker == "AAPL"

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_period_override(self, mock_ticker_cls):
        mt = _mock_ticker()
        mock_ticker_cls.return_value = mt
        client = YFinanceClient()
        client.get_market_data("AAPL", AssetType.STOCK, period="6mo")

        mt.history.assert_called_once_with(period="6mo", interval="1d")


class TestGetFinancials:
    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_income_statement_extracts_metrics(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            income_stmt=_make_income_stmt_df()
        )
        client = YFinanceClient()
        resp = client.get_financials(
            "AAPL", FinancialStatementType.INCOME_STATEMENT
        )

        assert isinstance(resp, FinancialStatementResponse)
        assert resp.ticker == "AAPL"
        assert resp.statement_type == FinancialStatementType.INCOME_STATEMENT
        assert len(resp.data) == 2
        r = resp.data[0]
        assert r.fiscal_year == 2024
        assert r.total_revenue == 500000.0
        assert r.net_income == 100000.0
        assert r.net_profit_margin == pytest.approx(0.2)

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_revenue_yoy_calculation(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            income_stmt=_make_income_stmt_df()
        )
        client = YFinanceClient()
        resp = client.get_financials(
            "AAPL", FinancialStatementType.INCOME_STATEMENT
        )

        latest = resp.data[0]
        assert latest.revenue_yoy == pytest.approx(0.25)
        oldest = resp.data[1]
        assert oldest.revenue_yoy is None

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_balance_sheet_extracts_metrics(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            balance_sheet=_make_balance_sheet_df()
        )
        client = YFinanceClient()
        resp = client.get_financials(
            "AAPL", FinancialStatementType.BALANCE_SHEET
        )

        assert len(resp.data) == 1
        r = resp.data[0]
        assert r.total_assets == 1000000.0
        assert r.total_liabilities == 400000.0
        assert r.total_equity == 600000.0

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_cashflow_extracts_metrics(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            cashflow=_make_cashflow_df()
        )
        client = YFinanceClient()
        resp = client.get_financials("AAPL", FinancialStatementType.CASH_FLOW)

        assert len(resp.data) == 1
        r = resp.data[0]
        assert r.operating_cash_flow == 150000.0
        assert r.free_cash_flow == 80000.0

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_quarterly_frequency(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            income_stmt=_make_income_stmt_df()
        )
        client = YFinanceClient()
        resp = client.get_financials(
            "AAPL",
            FinancialStatementType.INCOME_STATEMENT,
            frequency=DataFrequency.QUARTERLY,
        )

        for r in resp.data:
            assert r.fiscal_quarter is not None

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_empty_statement_returns_empty(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(income_stmt=pd.DataFrame())
        client = YFinanceClient()
        resp = client.get_financials(
            "AAPL", FinancialStatementType.INCOME_STATEMENT
        )

        assert len(resp.data) == 0


class TestGetAnalystData:
    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_parses_recommendations_and_earnings(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            upgrades=_make_upgrades_df(),
            earnings=_make_earnings_df(),
        )
        client = YFinanceClient()
        resp = client.get_analyst_data("AAPL")

        assert isinstance(resp, AnalystResponse)
        assert resp.ticker == "AAPL"
        assert len(resp.recommendations) == 2
        assert len(resp.earnings_estimates) == 2

        rec = resp.recommendations[0]
        assert isinstance(rec, AnalystRecommendation)
        assert rec.firm == "Goldman"
        assert rec.rating == "Buy"
        assert rec.rating_date == date(2025, 1, 10)

        est = resp.earnings_estimates[0]
        assert isinstance(est, EarningsEstimate)
        assert est.eps_estimate == 1.5
        assert est.eps_actual == 1.6

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_empty_data_returns_empty_lists(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(
            upgrades=pd.DataFrame(), earnings=pd.DataFrame()
        )
        client = YFinanceClient()
        resp = client.get_analyst_data("AAPL")

        assert len(resp.recommendations) == 0
        assert len(resp.earnings_estimates) == 0


class TestGetCompanyInfo:
    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_maps_info_dict_to_company_info(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker()
        client = YFinanceClient()
        info = client.get_company_info("AAPL")

        assert isinstance(info, CompanyInfo)
        assert info.ticker == "AAPL"
        assert info.name == "Test Corp"
        assert info.sector == "Technology"
        assert info.industry == "Software"
        assert info.country == "US"
        assert info.market_cap == 1e12
        assert info.employees == 50000
        assert info.founded_year == 2000

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_missing_fields_default_to_none(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(use_default_info=False)
        client = YFinanceClient()
        info = client.get_company_info("AAPL")

        assert info.name is None
        assert info.sector is None
        assert info.market_cap is None
        assert info.employees is None
        assert info.founded_year is None

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_exception_returns_minimal_company_info(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("fail")
        client = YFinanceClient()
        info = client.get_company_info("AAPL")

        assert info.ticker == "AAPL"
        assert info.name is None


class TestGetCryptoData:
    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_converts_crypto_history(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker()
        client = YFinanceClient()
        resp = client.get_crypto_data("BTC-USD")

        assert isinstance(resp, CryptoDataResponse)
        assert resp.ticker == "BTC-USD"
        assert len(resp.data) == 2
        p = resp.data[0]
        assert p.ticker == "BTC-USD"
        assert p.trade_date == date(2025, 1, 2)
        assert p.open == 100.0
        assert p.market_cap == 1e12

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_empty_history_returns_empty(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_ticker(history_df=pd.DataFrame())
        client = YFinanceClient()
        resp = client.get_crypto_data("BTC-USD")

        assert len(resp.data) == 0


class TestConfigIntegration:
    def test_default_config(self):
        client = YFinanceClient()
        assert client._config.history_period == "1y"

    def test_custom_config(self):
        config = YFinanceConfig(history_period="6m")
        client = YFinanceClient(config=config)
        assert client._config.history_period == "6m"

    @patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker")
    def test_config_period_used_as_default(self, mock_ticker_cls):
        mt = _mock_ticker()
        mock_ticker_cls.return_value = mt
        config = YFinanceConfig(history_period="3m")
        client = YFinanceClient(config=config)
        client.get_market_data("AAPL", AssetType.STOCK)

        mt.history.assert_called_once_with(period="3m", interval="1d")
