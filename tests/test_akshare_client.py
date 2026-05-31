from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from fin_agent.adapters.market_data.akshare import AKShareClient, AKShareConfig
from fin_agent.domain.constants import (
    AssetType,
    FinancialStatementType,
)
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementResponse,
    MarketDataResponse,
)


def _make_hist_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2025-01-02", "2025-01-03"],
            "开盘": [100.0, 101.5],
            "收盘": [101.0, 102.5],
            "最高": [102.0, 103.0],
            "最低": [99.0, 100.5],
            "成交量": [1000000, 1200000],
            "成交额": [101000000.0, 123000000.0],
            "换手率": [1.5, 1.8],
            "涨跌幅": [1.0, 1.49],
        }
    )


def _make_income_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "截止日期": ["2024-12-31", "2023-12-31"],
            "营业总收入": [500000.0, 400000.0],
            "净利润": [100000.0, 80000.0],
            "营业总收入同比增长率": [0.25, None],
            "净利润同比增长率": [0.25, None],
            "销售净利率": [0.2, 0.2],
        }
    )


def _make_balance_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "截止日期": ["2024-12-31"],
            "总资产": [1000000.0],
            "总负债": [400000.0],
            "所有者权益合计": [600000.0],
        }
    )


def _make_cashflow_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "截止日期": ["2024-12-31"],
            "经营活动产生的现金流量净额": [150000.0],
            "自由现金流量": [80000.0],
        }
    )


def _make_info_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "item": ["公司名称", "行业", "地区", "公司简介", "员工人数"],
            "value": ["贵州茅台", "白酒", "贵州", "白酒龙头", "25000"],
        }
    )


def _make_index_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2025-01-02", "2025-01-03"],
            "开盘": [3000.0, 3010.0],
            "收盘": [3010.0, 3020.0],
            "最高": [3020.0, 3030.0],
            "最低": [2990.0, 3000.0],
            "成交量": [5000000000, 5200000000],
        }
    )


class TestGetMarketData:
    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_zh_a_hist")
    def test_converts_hist_df_to_market_data_response(self, mock_hist):
        mock_hist.return_value = _make_hist_df()
        client = AKShareClient()
        resp = client.get_market_data("600519", AssetType.STOCK)

        assert isinstance(resp, MarketDataResponse)
        assert resp.ticker == "600519"
        assert resp.asset_type == AssetType.STOCK
        assert len(resp.data) == 2
        p = resp.data[0]
        assert p.trade_date == date(2025, 1, 2)
        assert p.open == 100.0
        assert p.high == 102.0
        assert p.low == 99.0
        assert p.close == 101.0
        assert p.volume == 1000000
        assert p.turnover == pytest.approx(101000000.0)

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_zh_a_hist")
    def test_empty_history_returns_empty(self, mock_hist):
        mock_hist.return_value = pd.DataFrame()
        client = AKShareClient()
        resp = client.get_market_data("600519", AssetType.STOCK)

        assert isinstance(resp, MarketDataResponse)
        assert len(resp.data) == 0

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_zh_a_hist")
    def test_exception_returns_empty(self, mock_hist):
        mock_hist.side_effect = Exception("network error")
        client = AKShareClient()
        resp = client.get_market_data("600519", AssetType.STOCK)

        assert len(resp.data) == 0
        assert resp.ticker == "600519"

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_zh_index_daily_em")
    def test_index_asset_type(self, mock_index):
        mock_index.return_value = _make_index_df()
        client = AKShareClient()
        resp = client.get_market_data("sh000300", AssetType.INDEX)

        assert isinstance(resp, MarketDataResponse)
        assert resp.asset_type == AssetType.INDEX
        assert len(resp.data) == 2


class TestGetFinancials:
    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_profit_sheet_by_report_em")
    def test_income_statement_extracts_metrics(self, mock_income):
        mock_income.return_value = _make_income_df()
        client = AKShareClient()
        resp = client.get_financials(
            "600519", FinancialStatementType.INCOME_STATEMENT
        )

        assert isinstance(resp, FinancialStatementResponse)
        assert len(resp.data) == 2
        r = resp.data[0]
        assert r.fiscal_year == 2024
        assert r.total_revenue == 500000.0
        assert r.net_income == 100000.0
        assert r.revenue_yoy == pytest.approx(0.25)
        assert r.net_profit_margin == pytest.approx(0.2)

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_balance_sheet_by_report_em")
    def test_balance_sheet_extracts_metrics(self, mock_balance):
        mock_balance.return_value = _make_balance_df()
        client = AKShareClient()
        resp = client.get_financials(
            "600519", FinancialStatementType.BALANCE_SHEET
        )

        assert len(resp.data) == 1
        r = resp.data[0]
        assert r.total_assets == 1000000.0
        assert r.total_liabilities == 400000.0
        assert r.total_equity == 600000.0

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_cash_flow_sheet_by_report_em")
    def test_cashflow_extracts_metrics(self, mock_cashflow):
        mock_cashflow.return_value = _make_cashflow_df()
        client = AKShareClient()
        resp = client.get_financials("600519", FinancialStatementType.CASH_FLOW)

        assert len(resp.data) == 1
        r = resp.data[0]
        assert r.operating_cash_flow == 150000.0
        assert r.free_cash_flow == 80000.0

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_profit_sheet_by_report_em")
    def test_empty_statement_returns_empty(self, mock_income):
        mock_income.return_value = pd.DataFrame()
        client = AKShareClient()
        resp = client.get_financials(
            "600519", FinancialStatementType.INCOME_STATEMENT
        )
        assert len(resp.data) == 0


class TestGetAnalystData:
    def test_analyst_data_disabled_returns_empty(self):
        client = AKShareClient()
        resp = client.get_analyst_data("600519")

        assert isinstance(resp, AnalystResponse)
        assert resp.ticker == "600519"
        assert resp.recommendations == []
        assert resp.earnings_estimates == []


class TestGetCompanyInfo:
    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_individual_info_em")
    def test_maps_info_df_to_company_info(self, mock_info):
        mock_info.return_value = _make_info_df()
        client = AKShareClient()
        info = client.get_company_info("600519")

        assert isinstance(info, CompanyInfo)
        assert info.ticker == "600519"
        assert info.name == "贵州茅台"
        assert info.industry == "白酒"
        assert info.country == "贵州"
        assert info.employees == 25000

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_individual_info_em")
    def test_empty_info_returns_minimal(self, mock_info):
        mock_info.return_value = pd.DataFrame()
        client = AKShareClient()
        info = client.get_company_info("600519")

        assert info.ticker == "600519"
        assert info.name is None

    @patch("fin_agent.adapters.market_data.akshare.client.ak.stock_individual_info_em")
    def test_exception_returns_minimal(self, mock_info):
        mock_info.side_effect = Exception("fail")
        client = AKShareClient()
        info = client.get_company_info("600519")

        assert info.ticker == "600519"
        assert info.name is None


class TestGetCryptoData:
    def test_returns_empty_since_akshare_has_no_crypto_hist(self):
        client = AKShareClient()
        resp = client.get_crypto_data("BTC")

        assert isinstance(resp, CryptoDataResponse)
        assert resp.ticker == "BTC"
        assert len(resp.data) == 0


class TestConfigIntegration:
    def test_default_config(self):
        client = AKShareClient()
        assert client._config.adjust == "qfq"
        assert client._config.history_period == "1y"

    def test_custom_config(self):
        config = AKShareConfig(adjust="hfq", history_period="3y")
        client = AKShareClient(config=config)
        assert client._config.adjust == "hfq"
        assert client._config.history_period == "3y"


class TestTickerNormalization:
    def test_sh_ticker(self):
        from fin_agent.adapters.market_data.akshare.client import _normalize_a_ticker
        assert _normalize_a_ticker("600519") == "sh600519"
        assert _normalize_a_ticker("sh600519") == "sh600519"

    def test_sz_ticker(self):
        from fin_agent.adapters.market_data.akshare.client import _normalize_a_ticker
        assert _normalize_a_ticker("000001") == "sz000001"
        assert _normalize_a_ticker("300001") == "sz300001"

    def test_bj_ticker(self):
        from fin_agent.adapters.market_data.akshare.client import _normalize_a_ticker
        assert _normalize_a_ticker("830001") == "bj830001"
