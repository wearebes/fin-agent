from __future__ import annotations

from datetime import date
from unittest.mock import patch

from fin_agent.adapters.market_data.fmp.client import FMPClient
from fin_agent.adapters.market_data.fmp.config import FMPConfig
from fin_agent.domain.constants import DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystRecommendation,
    CompanyInfo,
    FinancialStatementResponse,
)


def _client_with_key() -> FMPClient:
    return FMPClient(FMPConfig(api_key="test-key"))


class TestGetFinancials:
    @patch.object(FMPClient, "_get")
    def test_maps_income_statement_with_fiscal_year(self, mock_get):
        mock_get.return_value = [
            {
                "date": "2024-12-31",
                "revenue": 500000.0,
                "netIncome": 100000.0,
                "totalStockholdersEquity": 250000.0,
            },
            {"date": "2023-12-31", "revenue": 400000.0, "netIncome": 80000.0},
        ]
        client = _client_with_key()
        resp = client.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        assert isinstance(resp, FinancialStatementResponse)
        assert resp.statement_type == FinancialStatementType.INCOME_STATEMENT
        assert len(resp.data) == 2
        r = resp.data[0]
        assert r.fiscal_year == 2024
        assert r.fiscal_quarter is None
        assert r.statement_type == FinancialStatementType.INCOME_STATEMENT
        assert r.total_revenue == 500000.0
        assert r.net_income == 100000.0
        assert r.total_equity == 250000.0

    @patch.object(FMPClient, "_get")
    def test_quarterly_sets_fiscal_quarter(self, mock_get):
        mock_get.return_value = [{"date": "2024-09-30", "revenue": 120000.0}]
        client = _client_with_key()
        resp = client.get_financials(
            "AAPL",
            FinancialStatementType.INCOME_STATEMENT,
            frequency=DataFrequency.QUARTERLY,
        )

        assert resp.data[0].fiscal_year == 2024
        assert resp.data[0].fiscal_quarter == 3

    @patch.object(FMPClient, "_get")
    def test_skips_records_with_unparseable_date(self, mock_get):
        mock_get.return_value = [
            {"date": "", "revenue": 1.0},
            {"date": "2022-12-31", "revenue": 2.0},
        ]
        client = _client_with_key()
        resp = client.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)

        assert len(resp.data) == 1
        assert resp.data[0].fiscal_year == 2022

    @patch.object(FMPClient, "_get")
    def test_empty_or_non_list_returns_empty(self, mock_get):
        mock_get.return_value = None
        client = _client_with_key()
        resp = client.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)
        assert resp.data == []

    def test_no_api_key_returns_empty(self):
        client = FMPClient(FMPConfig(api_key=None))
        resp = client.get_financials("AAPL", FinancialStatementType.INCOME_STATEMENT)
        assert resp.data == []


class TestGetAnalystData:
    @patch.object(FMPClient, "_get")
    def test_maps_consensus_to_rating(self, mock_get):
        mock_get.return_value = [
            {"date": "2025-01-10", "consensus": "Buy", "targetPrice": 250.0},
            {"date": "bad-date", "consensus": "Hold", "targetPrice": None},
        ]
        client = _client_with_key()
        recs = client.get_analyst_data("AAPL")

        assert len(recs) == 2
        assert isinstance(recs[0], AnalystRecommendation)
        assert recs[0].rating == "Buy"
        assert recs[0].target_price == 250.0
        assert recs[0].rating_date == date(2025, 1, 10)
        # unparseable date degrades to None rather than raising
        assert recs[1].rating == "Hold"
        assert recs[1].rating_date is None

    @patch.object(FMPClient, "_get")
    def test_empty_returns_empty_list(self, mock_get):
        mock_get.return_value = None
        client = _client_with_key()
        assert client.get_analyst_data("AAPL") == []


class TestGetCompanyInfo:
    @patch.object(FMPClient, "_get")
    def test_maps_profile_fields(self, mock_get):
        mock_get.return_value = [
            {
                "companyName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "US",
                "description": "Designs and sells consumer electronics.",
                "mktCap": 3000000000000.0,
                "exchangeShortName": "NASDAQ",
            }
        ]
        client = _client_with_key()
        info = client.get_company_info("AAPL")

        assert isinstance(info, CompanyInfo)
        assert info.name == "Apple Inc."
        assert info.sector == "Technology"
        assert info.industry == "Consumer Electronics"
        assert info.country == "US"
        assert info.market_cap == 3000000000000.0

    @patch.object(FMPClient, "_get")
    def test_empty_returns_none(self, mock_get):
        mock_get.return_value = []
        client = _client_with_key()
        assert client.get_company_info("AAPL") is None
