from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.adapters.market_data.sina import _assignment, get_us_history
from fin_agent.adapters.market_data.yfinance.client import YFinanceClient
from fin_agent.domain.constants import AssetType
from fin_agent.domain.types import MarketDataResponse
from fin_agent.interfaces.api.forensics_router import build_forensics_router
from fin_agent.services.forensics import ForensicsService


def _row(day, close=100):
    return dict(
        date=day.isoformat(), open=close, high=close + 1, low=close - 1, close=close, volume=1000
    )


def _sina(rows, ticker="MU", factors=None):
    history = MagicMock(text='var prices="encoded";')
    adjustment = MagicMock(
        text='var factors={"data":[{"d":"1970-01-01","f":"0.5","c":"-1"}]}; /* checksum */'
    )
    if factors is not None:
        adjustment.text = factors
    with (
        patch(
            "fin_agent.adapters.market_data.sina.requests.get", side_effect=[history, adjustment]
        ) as http,
        patch("fin_agent.adapters.market_data.sina.MiniRacer") as decoder,
    ):
        decoder.return_value.__enter__.return_value.call.return_value = rows
        result = get_us_history(ticker, AssetType.STOCK, period="1y")
        return result, http


def test_adjustments_and_dates_are_not_invented():
    today = date.today()
    result, http = _sina([_row(today), _row(today - timedelta(days=500))])
    assert len(result.data) == 1
    assert result.data[0].close == 49
    assert result.currency == "USD"
    assert result.source == "Sina Finance"
    assert "not total return" in result.price_basis
    assert all(call.kwargs["timeout"] == 15 for call in http.call_args_list)


def test_index_is_not_replaced_with_an_etf_or_stock_adjustment():
    result, http = _sina([_row(date.today())], "^NDX")
    assert result.data[0].close == 100
    http.assert_called_once_with("https://finance.sina.com.cn/staticdata/us/.NDX", timeout=15)


@pytest.mark.parametrize(
    "rows,code",
    [
        ([], "no_data"),
        ([_row(date.today() - timedelta(days=12))], "stale"),
        ([_row(date.today() + timedelta(days=1))], "invalid_data"),
        ([_row(date.today(), 0)], "invalid_data"),
        ([_row(date.today()), _row(date.today(), 110)], "invalid_data"),
    ],
)
def test_unusable_prices_never_become_success(rows, code):
    result, _ = _sina(rows)
    assert not result.data
    assert result.error_code == code


def test_missing_adjustments_do_not_silently_fall_back_to_raw_prices():
    result, _ = _sina([_row(date.today())], factors='var factors={"data":[]}')
    assert not result.data and result.error_code == "invalid_data"
    assert _assignment('var x={"a":1}; /* checksum */') == {"a": 1}
    with pytest.raises(ValueError):
        _assignment('var x={"a":1}; malicious()')


def test_non_us_symbols_do_not_hit_us_endpoints():
    with patch("fin_agent.adapters.market_data.sina.requests.get") as http:
        for ticker in ("002594", "000660.KS", "0700.HK", "^HSI", "../../MU"):
            assert get_us_history(ticker, AssetType.STOCK).error_code == "unsupported"
        http.assert_not_called()


@pytest.mark.parametrize(
    "status,code",
    [(403, "restricted"), (429, "restricted"), (404, "no_data"), (500, "unavailable")],
)
def test_http_denial_is_not_reported_as_invalid_symbol(status, code):
    error = requests.HTTPError(response=SimpleNamespace(status_code=status))
    with patch("fin_agent.adapters.market_data.sina.requests.get", side_effect=error):
        assert get_us_history("MU", AssetType.STOCK).error_code == code
    with (
        patch("fin_agent.adapters.market_data.yfinance.client.yf.Ticker", side_effect=OSError()),
        patch(
            "fin_agent.adapters.market_data.yfinance.client.urlopen",
            side_effect=HTTPError("https://example.test", status, "provider error", {}, None),
        ),
    ):
        assert YFinanceClient().get_market_data("MU", AssetType.STOCK).error_code == code


def test_all_provider_failures_reach_ui_as_service_failure():
    empty = MarketDataResponse(ticker="MU", asset_type=AssetType.STOCK, error_code="restricted")
    with (
        patch("fin_agent.adapters.market_data.router.YFinanceClient") as yf,
        patch("fin_agent.adapters.market_data.router.get_us_history", return_value=empty),
    ):
        yf.return_value.get_market_data.return_value = empty
        router = MarketDataRouter()
        router._fmp._api_key = None
        app = FastAPI()
        app.state.container = SimpleNamespace(forensics_service=ForensicsService(router))
        app.include_router(build_forensics_router())
        response = TestClient(app).post("/v1/quant/forensics/runs", json={"ticker": "MU"})
    assert response.status_code == 503
    assert "限流" in response.json()["detail"]
    assert "不代表代码错误" in response.json()["detail"]
