"""Independent US daily history fallback; no credentials or fabricated prices.

Uses AKShare's installed decoder, not JavaScript supplied by the remote server.
Stock adjustment factors are parsed as JSON, never evaluated as Python/JS.
"""

from __future__ import annotations

import json
import logging
import math
import re
from bisect import bisect_right
from datetime import date, timedelta

import requests
from akshare.stock.cons import zh_js_decode
from py_mini_racer import MiniRacer

from fin_agent.domain.constants import AssetType, DataFrequency
from fin_agent.domain.types import MarketDataPoint, MarketDataResponse

logger = logging.getLogger(__name__)

_INDEX_SYMBOLS = {"^NDX": ".NDX", "^GSPC": ".INX", "^DJI": ".DJI", "^IXIC": ".IXIC"}
_PERIOD_DAYS = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "2y": 730,
    "3y": 1095,
    "5y": 1825,
    "10y": 3650,
}


def _assignment(text: str):
    # Only the RHS JSON/string literal is parsed; remote code is not executed.
    rhs = text.split("=", 1)[1].lstrip()
    value, end = json.JSONDecoder().raw_decode(rhs)
    if not re.fullmatch(r"\s*;?\s*(?:/\*.*?\*/\s*)?", rhs[end:], re.DOTALL):
        raise ValueError("Unexpected content after JSON assignment")
    return value


def get_us_history(
    ticker: str,
    asset_type: AssetType,
    *,
    frequency: DataFrequency = DataFrequency.DAILY,
    period: str | None = None,
) -> MarketDataResponse:
    ticker = ticker.strip().upper()
    response = MarketDataResponse(
        ticker=ticker,
        asset_type=asset_type,
        frequency=frequency,
        source="Sina Finance",
    )
    is_index = ticker in _INDEX_SYMBOLS
    if (
        frequency != DataFrequency.DAILY
        or (period or "1y") not in _PERIOD_DAYS
        or asset_type not in (AssetType.STOCK, AssetType.ETF, AssetType.INDEX)
        or (not is_index and not re.fullmatch(r"[A-Z]{1,6}(?:[.-][A-Z])?", ticker))
    ):
        response.error_code = "unsupported"
        return response
    symbol = _INDEX_SYMBOLS.get(ticker, ticker.replace("-", "."))
    end = date.today()
    start = end - timedelta(days=_PERIOD_DAYS[period or "1y"])
    try:
        raw = requests.get(f"https://finance.sina.com.cn/staticdata/us/{symbol}", timeout=15)
        raw.raise_for_status()
        encoded = _assignment(raw.text)
        if not isinstance(encoded, str):
            raise ValueError("Invalid encoded history")
        with MiniRacer() as decoder:
            decoder.eval(zh_js_decode)
            rows = decoder.call("d", encoded, timeout=5000)
        if not isinstance(rows, list) or not rows:
            response.error_code = "no_data"
            return response
        factors = []
        if not is_index:
            raw = requests.get(
                f"https://finance.sina.com.cn/us_stock/company/reinstatement/{symbol}_qfq.js",
                timeout=15,
            )
            raw.raise_for_status()
            factors = sorted(
                (date.fromisoformat(r["d"]), float(r["f"]), float(r["c"]))
                for r in _assignment(raw.text)["data"]
            )
            if (
                not factors
                or len({r[0] for r in factors}) != len(factors)
                or any(
                    not math.isfinite(f) or f <= 0 or not math.isfinite(c) for _, f, c in factors
                )
            ):
                raise ValueError("Missing or invalid adjustment factors")
        factor_dates = [r[0] for r in factors]
        points = {}
        for row in rows:
            day = date.fromisoformat(str(row["date"])[:10])
            if day > end:
                raise ValueError("Future price date")
            if day < start:
                continue
            factor, offset = 1.0, 0.0
            if not is_index:
                idx = bisect_right(factor_dates, day) - 1
                if idx < 0:
                    raise ValueError("Adjustment factors do not cover history")
                _, factor, offset = factors[idx]
            prices = {
                key: float(row[key]) * factor + offset for key in ("open", "high", "low", "close")
            }
            if (
                any(not math.isfinite(v) or v <= 0 for v in prices.values())
                or prices["low"] > min(prices["open"], prices["close"])
                or prices["high"] < max(prices["open"], prices["close"])
            ):
                raise ValueError("Invalid adjusted OHLC")
            volume = row.get("volume")
            point = MarketDataPoint(
                ticker=ticker,
                asset_type=asset_type,
                trade_date=day,
                **prices,
                volume=int(volume) if volume is not None else None,
            )
            if point.volume is not None and point.volume < 0:
                raise ValueError("Invalid volume")
            if day in points and points[day] != point:
                raise ValueError("Conflicting daily bars")
            points[day] = point
        response.data = sorted(points.values(), key=lambda p: p.trade_date)
        if not response.data:
            response.error_code = "no_data"
        elif (end - response.data[-1].trade_date).days > 7:
            # ponytail: conservative freshness guard; exchange calendars if needed.
            response.data = []
            response.error_code = "stale"
        response.currency = None if is_index else "USD"
        response.price_basis = (
            "Sina price index (not total return)"
            if is_index
            else "Sina forward-adjusted OHLC (price × qfq factor + offset; not total return)"
        )
    except requests.HTTPError as exc:
        status = exc.response.status_code
        response.error_code = (
            "no_data"
            if status == 404
            else "restricted"
            if status in (401, 403, 429)
            else "unavailable"
        )
    except requests.RequestException:
        response.error_code = "unavailable"
    except Exception as exc:
        logger.warning("Sina history validation failed for %s: %s", ticker, exc)
        response.error_code = "invalid_data"
    return response
