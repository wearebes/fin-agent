from __future__ import annotations

import logging
import re

from fin_agent.adapters.market_data.akshare.client import AKShareClient
from fin_agent.adapters.market_data.akshare.config import AKShareConfig
from fin_agent.adapters.market_data.fmp.client import FMPClient
from fin_agent.adapters.market_data.fmp.config import FMPConfig
from fin_agent.adapters.market_data.sina import get_us_history
from fin_agent.adapters.market_data.yfinance.client import YFinanceClient
from fin_agent.adapters.market_data.yfinance.config import YFinanceConfig
from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import (
    AnalystResponse,
    CompanyInfo,
    CryptoDataResponse,
    FinancialStatementResponse,
    MarketDataResponse,
)

logger = logging.getLogger(__name__)

_A_SHARE_RE = re.compile(
    r"^(?:(?P<prefix>sh|sz|bj))?(?P<code>\d{6})(?:\.(?P<suffix>ss|sz|bj))?$",
    re.IGNORECASE,
)
_SHANGHAI_INDEX_CODES = frozenset({"000001", "000016", "000300", "000688", "000852", "000905"})


def _is_a_share_ticker(ticker: str) -> bool:
    """纯 6 位大陆代码，或带 sh/sz/bj 前缀的 6 位代码。

    AAPL / 0700.HK / BTC-USD 均为 False。用于决定是否调用 AKShare
    （中国市场数据源），避免非 A 股 ticker 触发无效的中国接口调用。
    """
    return bool(ticker) and bool(_A_SHARE_RE.match(ticker.strip()))


def _a_share_code(ticker: str) -> str:
    match = _A_SHARE_RE.fullmatch(ticker.strip())
    return match.group("code") if match else ticker.strip()


def _yahoo_a_share_ticker(ticker: str) -> str:
    """Translate the app's six-digit A-share input into Yahoo's suffix format.

    The UI deliberately accepts familiar six-digit mainland symbols such as
    ``002594`` and ``000300``. Yahoo needs the exchange suffix only for the
    fallback request; users never need to type it.
    """
    match = _A_SHARE_RE.fullmatch(ticker.strip())
    if not match:
        return ticker.strip()
    code = match.group("code")
    market = (match.group("suffix") or match.group("prefix") or "").lower()
    if market:
        return f"{code}.{'SS' if market == 'sh' else market.upper()}"
    if code.startswith(("6", "9")) or code in _SHANGHAI_INDEX_CODES:
        suffix = ".SS"
    elif market == "bj" or code.startswith(("4", "8")):
        suffix = ".BJ"
    else:
        suffix = ".SZ"
    return f"{code}{suffix}"


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
            AssetType.STOCK,
            AssetType.ETF,
            AssetType.INDEX,
        )
        if is_a_share:
            code = _a_share_code(ticker)
            resp = self._ak.get_market_data(code, asset_type, frequency=frequency, period=period)
            if resp.data:
                resp.source = "AKShare"
                return resp
            # Yahoo is a reliable fallback for many A-share symbols, but it
            # requires an exchange suffix that is intentionally hidden from users.
            resp = self._yf.get_market_data(
                _yahoo_a_share_ticker(ticker),
                asset_type,
                frequency=frequency,
                period=period,
            )
            if resp.data:
                return resp
        if self._fmp._api_key:
            resp = self._fmp.get_market_data(ticker, asset_type, frequency=frequency, period=period)
            if resp.data:
                resp.source = "Financial Modeling Prep"
                return resp
        resp = self._yf.get_market_data(ticker, asset_type, frequency=frequency, period=period)
        if resp.data:
            return resp
        fallback = get_us_history(ticker, asset_type, frequency=frequency, period=period)
        if fallback.data:
            return fallback
        failures = {resp.error_code, fallback.error_code}
        resp.source = (
            "Yahoo Finance / Sina Finance" if fallback.error_code != "unsupported" else resp.source
        )
        resp.error_code = next(
            (
                code
                for code in ("invalid_data", "stale", "restricted", "unavailable")
                if code in failures
            ),
            "no_data",
        )
        return resp

    def get_financials(
        self,
        ticker: str,
        statement_type: FinancialStatementType,
        *,
        frequency: DataFrequency = DataFrequency.YEARLY,
    ) -> FinancialStatementResponse:
        # Financial arithmetic must never combine individual fields across providers.
        is_a_share = _is_a_share_ticker(ticker)
        providers = []
        if is_a_share:
            providers.append((self._ak, _a_share_code(ticker), "AKShare"))
        providers.append(
            (self._yf, _yahoo_a_share_ticker(ticker) if is_a_share else ticker, "Yahoo Finance")
        )
        if self._fmp._api_key:
            providers.append((self._fmp, ticker, "Financial Modeling Prep"))
        for provider, symbol, source in providers:
            try:
                response = provider.get_financials(symbol, statement_type, frequency=frequency)
                if response.data:
                    return response.model_copy(
                        update={
                            "ticker": ticker,
                            "source": response.source or source,
                            "data": [
                                r.model_copy(update={"ticker": ticker}) for r in response.data
                            ],
                        }
                    )
            except Exception:
                logger.warning("Financial source unavailable: %s", source)
        return FinancialStatementResponse(ticker=ticker, statement_type=statement_type)

    def get_analyst_data(self, ticker: str) -> AnalystResponse:
        # AKShare analyst data is disabled (stock_rank_forecast_cninfo no longer
        # exposes per-symbol ratings/EPS forecasts), so analyst data comes from
        # yfinance (and optionally FMP) for both A-share and non-A-share tickers.
        yahoo_ticker = _yahoo_a_share_ticker(ticker) if _is_a_share_ticker(ticker) else ticker
        merged = self._yf.get_analyst_data(yahoo_ticker)
        if self._fmp._api_key:
            fmp_recs = self._fmp.get_analyst_data(ticker)
            if fmp_recs:
                extra = AnalystResponse(ticker=ticker, recommendations=fmp_recs)
                merged = _merge_analyst_response(merged, extra)
        return merged

    def get_company_info(self, ticker: str) -> CompanyInfo:
        is_a_share = _is_a_share_ticker(ticker)
        yahoo_ticker = _yahoo_a_share_ticker(ticker) if is_a_share else ticker
        merged = self._yf.get_company_info(yahoo_ticker)
        if is_a_share:
            info_b = self._ak.get_company_info(_a_share_code(ticker))
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
        fallback: CryptoDataResponse = self._ak.get_crypto_data(ticker, period=period)
        return fallback
