from __future__ import annotations

import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fin_agent.domain.constants import AssetType, DataFrequency
from fin_agent.domain.forensics import CustomSignalKind, ForensicsRequest, StrategyKind
from fin_agent.domain.types import LLMMessage, LLMResponse, MarketDataPoint, MarketDataResponse
from fin_agent.interfaces.api.forensics_router import build_forensics_router
from fin_agent.services.forensics import ForensicsService, NoMarketDataError


def _series(ticker: str, *, count: int = 520, offset: float = 0.0) -> MarketDataResponse:
    start = date(2023, 1, 2)
    points: list[MarketDataPoint] = []
    for index in range(count):
        trend = 100 + index * 0.045
        cycle = math.sin(index / 13 + offset) * 4.5
        close = trend + cycle
        points.append(
            MarketDataPoint(
                ticker=ticker,
                asset_type=AssetType.STOCK,
                trade_date=start + timedelta(days=index),
                open=close - 0.2,
                high=close + 0.6,
                low=close - 0.7,
                close=close,
                volume=1_000_000 + index,
            )
        )
    return MarketDataResponse(
        ticker=ticker,
        asset_type=AssetType.STOCK,
        frequency=DataFrequency.DAILY,
        data=points,
    )


class FakeMarketData:
    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        del asset_type, frequency, period
        return _series(ticker, offset=0.25 if ticker == "SPY" else 0.0)


class ShortMarketData(FakeMarketData):
    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse:
        del asset_type, frequency, period
        return _series(ticker, count=80)


class FakeLLM:
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        del messages, temperature, max_tokens
        content = json.dumps(
            {
                "summary": "The audit remains evidence-bound.",
                "primary_cause": "Parameter fragility is the weakest check.",
                "repair_action": "Change one parameter and rerun the locked audit.",
            }
        )
        return LLMResponse(message=LLMMessage(role="assistant", content=content))


@pytest.mark.asyncio
async def test_forensics_report_is_complete_and_reproducible() -> None:
    service = ForensicsService(FakeMarketData())
    request = ForensicsRequest(
        ticker="TEST",
        benchmark="SPY",
        strategy=StrategyKind.MA_CROSS,
        fast_window=20,
        slow_window=60,
    )

    first = await service.diagnose(request)
    second = await service.diagnose(request)

    assert len(first.checks) == 6
    assert {check.key for check in first.checks} == {
        "leakage",
        "overfit",
        "sensitivity",
        "cost",
        "regime",
        "attribution",
    }
    assert len(first.sensitivity) == 5
    assert len(first.regimes) == 3
    assert len(first.equity_curve) <= 162
    assert first.metrics == second.metrics
    assert first.reliability_score == second.reliability_score
    assert first.narrative.generated_by_ai is False
    assert first.data_start < first.data_end


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", list(StrategyKind))
async def test_each_strategy_kind_produces_an_auditable_report(strategy: StrategyKind) -> None:
    request = ForensicsRequest(
        ticker="TEST",
        benchmark="SPY",
        strategy=strategy,
        custom_signal=CustomSignalKind.RSI,
        entry_threshold=30,
        exit_threshold=55,
        strategy_name="RSI 自定义规则",
    )

    report = await ForensicsService(FakeMarketData()).diagnose(request)

    assert report.strategy == strategy
    assert len(report.equity_curve) > 1
    assert len(report.checks) == 6
    if strategy == StrategyKind.CUSTOM:
        assert report.strategy_label == "RSI 自定义规则"


@pytest.mark.asyncio
async def test_llm_can_only_replace_narrative() -> None:
    request = ForensicsRequest(ticker="TEST", benchmark="SPY")
    deterministic = await ForensicsService(FakeMarketData()).diagnose(request)
    explained = await ForensicsService(FakeMarketData(), FakeLLM()).diagnose(request)

    assert explained.narrative.generated_by_ai is True
    assert explained.narrative.summary == "The audit remains evidence-bound."
    assert explained.metrics == deterministic.metrics
    assert explained.checks == deterministic.checks
    assert explained.reliability_score == deterministic.reliability_score


@pytest.mark.asyncio
async def test_forensics_without_benchmark_keeps_absolute_strategy_evaluation() -> None:
    report = await ForensicsService(FakeMarketData()).diagnose(
        ForensicsRequest(ticker="TEST", benchmark="")
    )

    assert report.benchmark is None
    assert report.benchmark_return_pct is None
    assert report.metrics.beta is None
    assert report.metrics.alpha_pct is None
    assert len(report.checks) == 5
    assert "attribution" not in {check.key for check in report.checks}
    assert all(point.benchmark is None for point in report.equity_curve)


def test_forensics_normalizes_common_index_aliases() -> None:
    request = ForensicsRequest(ticker="NDX100", benchmark="沪深300")

    assert request.ticker == "^NDX"
    assert request.benchmark == "000300"


@pytest.mark.asyncio
async def test_short_history_is_rejected() -> None:
    service = ForensicsService(ShortMarketData())
    with pytest.raises(NoMarketDataError, match="Not enough aligned history"):
        await service.diagnose(ForensicsRequest(ticker="TEST", benchmark="SPY"))


def test_fast_window_must_be_smaller_than_slow_window() -> None:
    with pytest.raises(ValidationError, match="fast_window must be smaller"):
        ForensicsRequest(fast_window=60, slow_window=20)


def test_custom_rsi_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="entry below exit"):
        ForensicsRequest(
            strategy=StrategyKind.CUSTOM,
            custom_signal=CustomSignalKind.RSI,
            entry_threshold=60,
            exit_threshold=40,
        )


def _api(service: ForensicsService) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(forensics_service=service)
    app.include_router(build_forensics_router())
    return app


def test_forensics_api_returns_report() -> None:
    with TestClient(_api(ForensicsService(FakeMarketData()))) as client:
        response = client.post(
            "/v1/quant/forensics/runs",
            json={"ticker": "TEST", "benchmark": "SPY", "period": "2y"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "TEST"
    assert len(payload["checks"]) == 6


def test_forensics_api_accepts_an_empty_optional_benchmark() -> None:
    with TestClient(_api(ForensicsService(FakeMarketData()))) as client:
        response = client.post(
            "/v1/quant/forensics/runs",
            json={"ticker": "TEST", "benchmark": "", "period": "2y"},
        )

    assert response.status_code == 200
    assert response.json()["benchmark"] is None


def test_forensics_api_explains_missing_history() -> None:
    with TestClient(_api(ForensicsService(ShortMarketData()))) as client:
        response = client.post(
            "/v1/quant/forensics/runs",
            json={"ticker": "TEST", "benchmark": "SPY", "period": "2y"},
        )

    assert response.status_code == 422
    assert "Not enough aligned history" in response.json()["detail"]
