"""Evidence-first backtest diagnostics for the Quant Forensics UI.

The numerical result is produced only from observed daily closing prices.  The
LLM is deliberately downstream: it may explain a completed audit, but cannot
alter returns, scores, or verdicts.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import uuid4

from fin_agent.domain.constants import AssetType, DataFrequency
from fin_agent.domain.forensics import (
    AuditCheck,
    AuditStatus,
    CostScenario,
    CustomSignalKind,
    EquityPoint,
    ForensicsNarrative,
    ForensicsReport,
    ForensicsRequest,
    PerformanceMetrics,
    RegimeResult,
    SensitivityPoint,
    StrategyKind,
)
from fin_agent.domain.types import LLMMessage, LLMResponse, MarketDataResponse


class MarketDataSource(Protocol):
    def get_market_data(
        self,
        ticker: str,
        asset_type: AssetType,
        *,
        frequency: DataFrequency = DataFrequency.DAILY,
        period: str | None = None,
    ) -> MarketDataResponse: ...


class NarrativeLLM(Protocol):
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...


class NoMarketDataError(ValueError):
    pass


def _pct(value: float) -> float:
    return round(value * 100, 2)


def _safe_mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _compound(returns: Sequence[float]) -> float:
    value = 1.0
    for item in returns:
        value *= 1.0 + item
    return value - 1.0


def _annualized(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0
    gross = max(0.000001, 1.0 + _compound(returns))
    return gross ** (252 / len(returns)) - 1.0


def _max_drawdown(returns: Sequence[float]) -> float:
    equity = peak = 1.0
    worst = 0.0
    for item in returns:
        equity *= 1.0 + item
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def _equity(returns: Sequence[float]) -> list[float]:
    values: list[float] = []
    current = 100.0
    for item in returns:
        current *= 1.0 + item
        values.append(current)
    return values


def _moving_average(values: Sequence[float], end: int, window: int) -> float | None:
    start = end - window
    if start < 0:
        return None
    return _safe_mean(values[start:end])


def _ema(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    alpha = 2 / (len(values) + 1)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1 - alpha) * value
    return value


def _rsi(values: Sequence[float], end: int, window: int) -> float | None:
    start = end - window - 1
    if start < 0:
        return None
    changes = [values[index] - values[index - 1] for index in range(start + 1, end)]
    gains = [max(0.0, change) for change in changes]
    losses = [max(0.0, -change) for change in changes]
    average_loss = _safe_mean(losses)
    if average_loss == 0:
        return 100.0
    relative_strength = _safe_mean(gains) / average_loss
    return 100 - 100 / (1 + relative_strength)


def _momentum(values: Sequence[float], end: int, window: int) -> float | None:
    start = end - window - 1
    if start < 0 or values[start] == 0:
        return None
    return (values[end - 1] / values[start] - 1) * 100


def _signals(
    closes: Sequence[float],
    kind: StrategyKind,
    fast: int,
    slow: int,
    *,
    custom_signal: CustomSignalKind = CustomSignalKind.MA_CROSS,
    entry_threshold: float = 0.2,
    exit_threshold: float = 0.0,
    lagged: bool = True,
) -> list[float]:
    result = [0.0] * len(closes)
    held = 0.0
    for i in range(1, len(closes)):
        end = i if lagged else i + 1
        fast_ma = _moving_average(closes, end, fast)
        slow_ma = _moving_average(closes, end, slow)
        if fast_ma is None or slow_ma is None:
            continue
        if kind == StrategyKind.MA_CROSS:
            held = 1.0 if fast_ma > slow_ma else 0.0
        elif kind == StrategyKind.BREAKOUT:
            reference = closes[end - 1]
            prior_start = max(0, end - slow)
            prior = closes[prior_start : end - 1]
            exit_ma = _moving_average(closes, end, fast)
            if prior and reference > max(prior):
                held = 1.0
            elif exit_ma is not None and reference < exit_ma:
                held = 0.0
        elif kind == StrategyKind.MEAN_REVERSION:
            window = closes[end - slow : end]
            sigma = _std(window)
            z_score = 0.0 if sigma == 0 else (closes[end - 1] - _safe_mean(window)) / sigma
            if z_score < -1.0:
                held = 1.0
            elif z_score > 0.0:
                held = 0.0
        elif kind == StrategyKind.RSI_REVERSION:
            rsi = _rsi(closes, end, fast)
            if rsi is not None and rsi < 30:
                held = 1.0
            elif rsi is not None and rsi > 55:
                held = 0.0
        elif kind == StrategyKind.MOMENTUM_TREND:
            momentum = _momentum(closes, end, fast)
            if momentum is not None:
                held = 1.0 if momentum > 0 and closes[end - 1] > slow_ma else 0.0
        elif kind == StrategyKind.BOLLINGER_REVERSION:
            window = closes[end - slow : end]
            sigma = _std(window)
            z_score = 0.0 if sigma == 0 else (closes[end - 1] - _safe_mean(window)) / sigma
            if z_score < -2.0:
                held = 1.0
            elif z_score >= 0:
                held = 0.0
        elif custom_signal == CustomSignalKind.MA_CROSS:
            spread = (fast_ma / slow_ma - 1) * 100 if slow_ma else 0.0
            if spread >= entry_threshold:
                held = 1.0
            elif spread <= exit_threshold:
                held = 0.0
        elif custom_signal == CustomSignalKind.RSI:
            rsi = _rsi(closes, end, fast)
            if rsi is not None and rsi <= entry_threshold:
                held = 1.0
            elif rsi is not None and rsi >= exit_threshold:
                held = 0.0
        elif custom_signal == CustomSignalKind.MOMENTUM:
            momentum = _momentum(closes, end, fast)
            if momentum is not None and momentum >= entry_threshold:
                held = 1.0
            elif momentum is not None and momentum <= exit_threshold:
                held = 0.0
        else:
            window = closes[end - slow : end]
            sigma = _std(window)
            z_score = 0.0 if sigma == 0 else (closes[end - 1] - _safe_mean(window)) / sigma
            if z_score <= -abs(entry_threshold):
                held = 1.0
            elif z_score >= exit_threshold:
                held = 0.0
        result[i] = held
    return result


def _signals_for_request(
    closes: Sequence[float],
    request: ForensicsRequest,
    *,
    fast: int | None = None,
    slow: int | None = None,
    lagged: bool = True,
) -> list[float]:
    return _signals(
        closes,
        request.strategy,
        fast if fast is not None else request.fast_window,
        slow if slow is not None else request.slow_window,
        custom_signal=request.custom_signal,
        entry_threshold=request.entry_threshold,
        exit_threshold=request.exit_threshold,
        lagged=lagged,
    )


def _strategy_returns(
    closes: Sequence[float], signals: Sequence[float], cost_bps: float
) -> tuple[list[float], int]:
    returns = [0.0] * len(closes)
    trades = 0
    cost = cost_bps / 10000.0
    for i in range(1, len(closes)):
        raw = closes[i] / closes[i - 1] - 1.0
        turnover = abs(signals[i] - signals[i - 1])
        if turnover:
            trades += 1
        returns[i] = signals[i] * raw - turnover * cost
    return returns, trades


def _beta_alpha(strategy: Sequence[float], benchmark: Sequence[float]) -> tuple[float, float]:
    if len(strategy) < 3 or len(strategy) != len(benchmark):
        return 0.0, 0.0
    bench_mean = _safe_mean(benchmark)
    strat_mean = _safe_mean(strategy)
    variance = sum((x - bench_mean) ** 2 for x in benchmark) / (len(benchmark) - 1)
    if variance == 0:
        return 0.0, strat_mean * 252
    covariance = sum(
        (x - bench_mean) * (y - strat_mean) for x, y in zip(benchmark, strategy, strict=True)
    ) / (len(benchmark) - 1)
    beta = covariance / variance
    alpha = (strat_mean - beta * bench_mean) * 252
    return beta, alpha


def _status(score: int, *, warning_at: int = 60) -> AuditStatus:
    if score >= 75:
        return AuditStatus.PASS
    if score >= warning_at:
        return AuditStatus.WARNING
    return AuditStatus.FAIL


class ForensicsService:
    def __init__(self, market_data: MarketDataSource, llm: NarrativeLLM | None = None) -> None:
        self._market_data = market_data
        self._llm = llm

    async def diagnose(self, request: ForensicsRequest) -> ForensicsReport:
        asset = self._load(request.ticker, request.period)
        benchmark = (
            asset
            if request.ticker.strip().upper() == request.benchmark.strip().upper()
            else self._load(request.benchmark, request.period)
        )
        dates, closes, bench_closes = self._align(asset, benchmark)
        if len(closes) < request.slow_window + 60:
            raise NoMarketDataError(
                f"Not enough aligned history for {request.ticker}; "
                f"need at least {request.slow_window + 60} daily observations."
            )

        signals = _signals_for_request(closes, request)
        strategy_returns, trades = _strategy_returns(closes, signals, request.transaction_cost_bps)
        benchmark_returns = [0.0] + [
            bench_closes[i] / bench_closes[i - 1] - 1.0 for i in range(1, len(bench_closes))
        ]

        sensitivity = self._sensitivity(request, closes)
        costs = self._cost_scenarios(request, closes, signals)
        regimes = self._regime_results(strategy_returns, benchmark_returns)
        checks = self._checks(
            request,
            closes,
            strategy_returns,
            benchmark_returns,
            sensitivity,
            costs,
            regimes,
        )
        reliability = round(_safe_mean([float(check.score) for check in checks]))
        verdict = self._verdict(reliability, request.lang)
        metrics = self._metrics(strategy_returns, benchmark_returns, trades)
        narrative = self._fallback_narrative(checks, reliability, request.lang)
        narrative = await self._ai_narrative(request, metrics, checks, narrative)

        strategy_equity = _equity(strategy_returns)
        benchmark_equity = _equity(benchmark_returns)
        stride = max(1, math.ceil(len(dates) / 160))
        curve = [
            EquityPoint(
                date=dates[i],
                strategy=round(strategy_equity[i], 2),
                benchmark=round(benchmark_equity[i], 2),
            )
            for i in range(0, len(dates), stride)
        ]
        if curve[-1].date != dates[-1]:
            curve.append(
                EquityPoint(
                    date=dates[-1],
                    strategy=round(strategy_equity[-1], 2),
                    benchmark=round(benchmark_equity[-1], 2),
                )
            )

        return ForensicsReport(
            run_id=f"qf_{uuid4().hex[:12]}",
            created_at=datetime.now(UTC).isoformat(),
            ticker=request.ticker.upper(),
            benchmark=request.benchmark.upper(),
            period=request.period,
            strategy=request.strategy,
            strategy_label=self._strategy_label(request),
            data_start=dates[0],
            data_end=dates[-1],
            observation_count=len(dates),
            reliability_score=reliability,
            verdict=verdict,
            metrics=metrics,
            benchmark_return_pct=_pct(_compound(benchmark_returns)),
            checks=checks,
            sensitivity=sensitivity,
            cost_scenarios=costs,
            regimes=regimes,
            equity_curve=curve,
            narrative=narrative,
            disclaimer=(
                "仅供研究与教学使用；结果基于历史收盘价和简化成交假设，"
                "不构成投资建议或未来收益保证。"
                if request.lang == "zh"
                else "For research and education only. Results use historical closes "
                "and simplified execution assumptions; they are not investment advice."
            ),
        )

    def _load(self, ticker: str, period: str) -> MarketDataResponse:
        result = self._market_data.get_market_data(
            ticker.strip().upper(),
            AssetType.STOCK,
            frequency=DataFrequency.DAILY,
            period=period,
        )
        if not result.data:
            raise NoMarketDataError(f"No daily market data returned for {ticker}.")
        return result

    @staticmethod
    def _align(
        asset: MarketDataResponse, benchmark: MarketDataResponse
    ) -> tuple[list[date], list[float], list[float]]:
        asset_map = {point.trade_date: point.close for point in asset.data if point.close > 0}
        bench_map = {point.trade_date: point.close for point in benchmark.data if point.close > 0}
        dates = sorted(set(asset_map) & set(bench_map))
        return dates, [asset_map[d] for d in dates], [bench_map[d] for d in dates]

    @staticmethod
    def _metrics(
        strategy: Sequence[float], benchmark: Sequence[float], trades: int
    ) -> PerformanceMetrics:
        volatility = _std(strategy) * math.sqrt(252)
        sharpe = 0.0 if volatility == 0 else _safe_mean(strategy) * 252 / volatility
        active_days = [item for item in strategy if item != 0]
        wins = sum(1 for item in active_days if item > 0)
        beta, alpha = _beta_alpha(strategy, benchmark)
        return PerformanceMetrics(
            total_return_pct=_pct(_compound(strategy)),
            annualized_return_pct=_pct(_annualized(strategy)),
            annualized_volatility_pct=_pct(volatility),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown_pct=_pct(_max_drawdown(strategy)),
            win_rate_pct=round(100 * wins / len(active_days), 2) if active_days else 0.0,
            trade_count=trades,
            beta=round(beta, 2),
            alpha_pct=_pct(alpha),
        )

    @staticmethod
    def _sensitivity(request: ForensicsRequest, closes: Sequence[float]) -> list[SensitivityPoint]:
        variants = [(0.8, "-20%"), (0.9, "-10%"), (1.0, "基准"), (1.1, "+10%"), (1.2, "+20%")]
        result: list[SensitivityPoint] = []
        for ratio, label in variants:
            fast = max(3, round(request.fast_window * ratio))
            slow = max(fast + 5, round(request.slow_window * ratio))
            signals = _signals_for_request(closes, request, fast=fast, slow=slow)
            returns, _ = _strategy_returns(closes, signals, request.transaction_cost_bps)
            result.append(
                SensitivityPoint(
                    label=label,
                    fast_window=fast,
                    slow_window=slow,
                    total_return_pct=_pct(_compound(returns)),
                )
            )
        return result

    @staticmethod
    def _cost_scenarios(
        request: ForensicsRequest,
        closes: Sequence[float],
        signals: Sequence[float],
    ) -> list[CostScenario]:
        levels = sorted({0.0, request.transaction_cost_bps, request.transaction_cost_bps * 2, 25.0})
        return [
            CostScenario(
                cost_bps=round(level, 1),
                total_return_pct=_pct(_compound(_strategy_returns(closes, signals, level)[0])),
            )
            for level in levels
        ]

    @staticmethod
    def _regime_results(
        strategy: Sequence[float], benchmark: Sequence[float]
    ) -> list[RegimeResult]:
        rolling_vol: list[float] = []
        for i in range(len(benchmark)):
            window = benchmark[max(0, i - 20) : i + 1]
            rolling_vol.append(_std(window))
        median_vol = statistics.median(rolling_vol)
        buckets: dict[str, list[float]] = {"bull": [], "bear": [], "high_vol": []}
        for i, value in enumerate(strategy):
            if rolling_vol[i] > median_vol * 1.35:
                buckets["high_vol"].append(value)
            elif _safe_mean(benchmark[max(0, i - 20) : i + 1]) >= 0:
                buckets["bull"].append(value)
            else:
                buckets["bear"].append(value)
        return [
            RegimeResult(
                regime=name,
                trading_days=len(values),
                annualized_return_pct=_pct(_annualized(values)),
            )
            for name, values in buckets.items()
        ]

    def _checks(
        self,
        request: ForensicsRequest,
        closes: Sequence[float],
        strategy: Sequence[float],
        benchmark: Sequence[float],
        sensitivity: Sequence[SensitivityPoint],
        costs: Sequence[CostScenario],
        regimes: Sequence[RegimeResult],
    ) -> list[AuditCheck]:
        lang = request.lang
        leaky_signals = _signals_for_request(closes, request, lagged=False)
        leaky_returns, _ = _strategy_returns(closes, leaky_signals, request.transaction_cost_bps)
        leakage_uplift = _pct(_compound(leaky_returns) - _compound(strategy))
        leakage_score = max(70, round(96 - max(0.0, leakage_uplift) * 0.4))

        sensitivity_returns = [point.total_return_pct for point in sensitivity]
        base_abs = max(5.0, abs(sensitivity_returns[2]))
        sensitivity_dispersion = _std(sensitivity_returns) / base_abs
        sensitivity_score = max(0, min(100, round(100 - sensitivity_dispersion * 95)))

        fold_size = len(strategy) // 3
        folds = [_pct(_compound(strategy[i * fold_size : (i + 1) * fold_size])) for i in range(3)]
        positive_folds = sum(1 for value in folds if value > 0)
        overfit_score = max(0, min(100, 25 + positive_folds * 22 - round(_std(folds) * 0.35)))

        zero_cost = next(item.total_return_pct for item in costs if item.cost_bps == 0)
        worst_cost = costs[-1].total_return_pct
        cost_drag = zero_cost - worst_cost
        cost_score = max(0, min(100, round(100 - max(0.0, cost_drag) * 2.2)))

        regime_returns = [item.annualized_return_pct for item in regimes if item.trading_days >= 10]
        regime_score = (
            50
            if not regime_returns
            else max(
                0,
                min(
                    100,
                    round(
                        75
                        + sum(1 for value in regime_returns if value > 0) * 8
                        - _std(regime_returns) * 0.45
                    ),
                ),
            )
        )

        beta, alpha = _beta_alpha(strategy, benchmark)
        attribution_score = max(
            0, min(100, round(78 - abs(beta) * 22 + max(-15, min(20, alpha * 100))))
        )

        if lang == "zh":
            return [
                AuditCheck(
                    key="leakage",
                    title="未来数据泄漏",
                    status=_status(leakage_score),
                    score=leakage_score,
                    finding="信号已强制滞后一日，未发现直接偷看未来价格。",
                    evidence=f"若错误使用当日价格，累计收益将变化 {leakage_uplift:+.2f} 个百分点。",
                ),
                AuditCheck(
                    key="overfit",
                    title="时间分段稳定性",
                    status=_status(overfit_score),
                    score=overfit_score,
                    finding=f"三个时间分段中有 {positive_folds}/3 个获得正收益。",
                    evidence="各段累计收益：" + " / ".join(f"{value:+.1f}%" for value in folds),
                ),
                AuditCheck(
                    key="sensitivity",
                    title="参数脆弱性",
                    status=_status(sensitivity_score),
                    score=sensitivity_score,
                    finding="检测参数上下浮动 10%–20% 后的收益稳定性。",
                    evidence=f"五组参数收益离散度为 {_std(sensitivity_returns):.2f} 个百分点。",
                ),
                AuditCheck(
                    key="cost",
                    title="交易成本悬崖",
                    status=_status(cost_score),
                    score=cost_score,
                    finding="比较零成本、设定成本、双倍成本与 25bps 压力情景。",
                    evidence=f"零成本至最严压力情景拖累 {cost_drag:.2f} 个百分点。",
                ),
                AuditCheck(
                    key="regime",
                    title="市场状态依赖",
                    status=_status(regime_score),
                    score=regime_score,
                    finding="分别检查上涨、下跌和高波动时期的策略表现。",
                    evidence=" / ".join(
                        f"{item.regime}: {item.annualized_return_pct:+.1f}%" for item in regimes
                    ),
                ),
                AuditCheck(
                    key="attribution",
                    title="Alpha 归因",
                    status=_status(attribution_score),
                    score=attribution_score,
                    finding="剥离基准方向暴露后检查剩余收益。",
                    evidence=f"估算 Beta {beta:.2f}，年化 Alpha {_pct(alpha):+.2f}%。",
                ),
            ]
        return [
            AuditCheck(
                key="leakage",
                title="Look-ahead leakage",
                status=_status(leakage_score),
                score=leakage_score,
                finding=(
                    "Signals are lagged by one session; no direct future-price access was found."
                ),
                evidence=(
                    "Using same-day prices incorrectly would change return by "
                    f"{leakage_uplift:+.2f} points."
                ),
            ),
            AuditCheck(
                key="overfit",
                title="Chronological stability",
                status=_status(overfit_score),
                score=overfit_score,
                finding=f"{positive_folds}/3 chronological folds produced positive returns.",
                evidence="Fold returns: " + " / ".join(f"{value:+.1f}%" for value in folds),
            ),
            AuditCheck(
                key="sensitivity",
                title="Parameter fragility",
                status=_status(sensitivity_score),
                score=sensitivity_score,
                finding="Tests 10%–20% perturbations around both strategy windows.",
                evidence=f"Return dispersion is {_std(sensitivity_returns):.2f} percentage points.",
            ),
            AuditCheck(
                key="cost",
                title="Cost cliff",
                status=_status(cost_score),
                score=cost_score,
                finding="Compares zero, configured, double, and 25bps execution costs.",
                evidence=f"Stress-cost drag is {cost_drag:.2f} percentage points.",
            ),
            AuditCheck(
                key="regime",
                title="Regime dependence",
                status=_status(regime_score),
                score=regime_score,
                finding="Separates bull, bear, and high-volatility sessions.",
                evidence=" / ".join(
                    f"{item.regime}: {item.annualized_return_pct:+.1f}%" for item in regimes
                ),
            ),
            AuditCheck(
                key="attribution",
                title="Alpha attribution",
                status=_status(attribution_score),
                score=attribution_score,
                finding="Estimates residual return after benchmark direction exposure.",
                evidence=f"Estimated beta {beta:.2f}; annualized alpha {_pct(alpha):+.2f}%.",
            ),
        ]

    @staticmethod
    def _verdict(score: int, lang: str) -> str:
        if lang == "zh":
            return (
                "可继续研究"
                if score >= 75
                else "存在明显脆弱性"
                if score >= 55
                else "不建议进入模拟盘"
            )
        return (
            "Researchable"
            if score >= 75
            else "Materially fragile"
            if score >= 55
            else "Do not paper-trade yet"
        )

    @staticmethod
    def _strategy_label(request: ForensicsRequest) -> str:
        labels = {
            StrategyKind.MA_CROSS: ("双均线趋势", "Dual moving average"),
            StrategyKind.BREAKOUT: ("区间突破", "Range breakout"),
            StrategyKind.MEAN_REVERSION: ("均值回归", "Mean reversion"),
            StrategyKind.RSI_REVERSION: ("RSI 反转", "RSI reversal"),
            StrategyKind.MOMENTUM_TREND: ("动量趋势", "Momentum trend"),
            StrategyKind.BOLLINGER_REVERSION: ("布林带反转", "Bollinger reversion"),
            StrategyKind.CUSTOM: ("自定义规则", "Custom rule"),
        }
        if request.strategy == StrategyKind.CUSTOM and request.strategy_name.strip():
            return request.strategy_name.strip()
        return labels[request.strategy][0 if request.lang == "zh" else 1]

    @staticmethod
    def _fallback_narrative(
        checks: Sequence[AuditCheck], score: int, lang: str
    ) -> ForensicsNarrative:
        weakest = min(checks, key=lambda item: item.score)
        if lang == "zh":
            return ForensicsNarrative(
                summary=(
                    f"该策略可信度为 {score}/100，当前结论："
                    f"{ForensicsService._verdict(score, lang)}。"
                ),
                primary_cause=f"最薄弱环节是“{weakest.title}”（{weakest.score}/100）。",
                repair_action="先只修复这一项，再以完全相同的数据切分重新审计，避免同时调整多个参数。",
            )
        return ForensicsNarrative(
            summary=(
                f"Reliability is {score}/100. Verdict: {ForensicsService._verdict(score, lang)}."
            ),
            primary_cause=f"The weakest dimension is {weakest.title} ({weakest.score}/100).",
            repair_action=(
                "Repair only this issue, then rerun the same locked audit before "
                "changing anything else."
            ),
        )

    async def _ai_narrative(
        self,
        request: ForensicsRequest,
        metrics: PerformanceMetrics,
        checks: Sequence[AuditCheck],
        fallback: ForensicsNarrative,
    ) -> ForensicsNarrative:
        if self._llm is None:
            return fallback
        payload = {
            "ticker": request.ticker,
            "strategy": request.strategy.value,
            "metrics": metrics.model_dump(),
            "checks": [check.model_dump(mode="json") for check in checks],
        }
        language = "Simplified Chinese" if request.lang == "zh" else "English"
        response = await self._llm.chat(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "You explain a completed quantitative strategy audit. Never alter numbers, "
                        "promise returns, or add facts. Return JSON only with three short strings: "
                        "summary, primary_cause, repair_action. Use " + language + "."
                    ),
                ),
                LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ],
            temperature=0.1,
            max_tokens=320,
        )
        content = response.message.content.strip()
        if not content:
            return fallback
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        try:
            parsed = json.loads(content)
            if not all(
                isinstance(parsed.get(key), str)
                for key in ("summary", "primary_cause", "repair_action")
            ):
                return fallback
            return ForensicsNarrative(
                summary=parsed["summary"],
                primary_cause=parsed["primary_cause"],
                repair_action=parsed["repair_action"],
                generated_by_ai=True,
            )
        except (json.JSONDecodeError, TypeError):
            return fallback
