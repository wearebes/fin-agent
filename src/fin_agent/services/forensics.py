"""Evidence-first backtest diagnostics for the Quant Forensics UI.

The numerical result is produced only from observed daily closing prices.  The
LLM is deliberately downstream: it may explain a completed audit, but cannot
alter returns, scores, or verdicts.
"""

from __future__ import annotations

import json
import logging
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
    ValidationFold,
    WalkForwardResult,
)
from fin_agent.domain.types import LLMMessage, LLMResponse, MarketDataResponse

logger = logging.getLogger(__name__)


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


def _rsi(values: Sequence[float], end: int, window: int) -> float | None:
    start = end - window - 1
    if start < 0:
        return None
    changes = [values[index] - values[index - 1] for index in range(start + 1, end)]
    gains = [max(0.0, change) for change in changes]
    losses = [max(0.0, -change) for change in changes]
    average_loss = _safe_mean(losses)
    if average_loss == 0:
        return 50.0 if _safe_mean(gains) == 0 else 100.0
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
) -> list[float]:
    result = [0.0] * len(closes)
    held = 0.0
    for i in range(1, len(closes)):
        end = i
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
) -> list[float]:
    return _signals(
        closes,
        request.strategy,
        fast if fast is not None else request.fast_window,
        slow if slow is not None else request.slow_window,
        custom_signal=request.custom_signal,
        entry_threshold=request.entry_threshold,
        exit_threshold=request.exit_threshold,
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
        # Signals[i] uses data through i-1, executes at close i, earns from i+1.
        returns[i] = (1 + signals[i - 1] * raw) * (1 - turnover * cost) - 1
    return returns, trades


def _beta_alpha(
    strategy: Sequence[float], benchmark: Sequence[float]
) -> tuple[float | None, float | None]:
    if len(strategy) < 3 or len(strategy) != len(benchmark):
        return None, None
    bench_mean = _safe_mean(benchmark)
    strat_mean = _safe_mean(strategy)
    variance = sum((x - bench_mean) ** 2 for x in benchmark) / (len(benchmark) - 1)
    if variance == 0:
        return None, None
    covariance = sum(
        (x - bench_mean) * (y - strat_mean) for x, y in zip(benchmark, strategy, strict=True)
    ) / (len(benchmark) - 1)
    beta = covariance / variance
    alpha = (strat_mean - beta * bench_mean) * 252
    return beta, alpha


class ForensicsService:
    def __init__(self, market_data: MarketDataSource, llm: NarrativeLLM | None = None) -> None:
        self._market_data = market_data
        self._llm = llm

    async def diagnose(self, request: ForensicsRequest) -> ForensicsReport:
        asset = self._load(request.ticker, request.period)
        benchmark = None
        if request.benchmark:
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
        validation = self._walk_forward(request, dates, closes)
        asset_returns = [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        benchmark_returns = (
            [0.0]
            + [bench_closes[i] / bench_closes[i - 1] - 1.0 for i in range(1, len(bench_closes))]
            if bench_closes is not None
            else None
        )

        sensitivity = self._sensitivity(request, closes)
        costs = self._cost_scenarios(request, closes, signals)
        start = request.slow_window
        regimes = self._regime_results(
            strategy_returns[start:], (benchmark_returns or asset_returns)[start:]
        )
        checks = self._checks(
            request,
            closes,
            strategy_returns,
            benchmark_returns,
            sensitivity,
            costs,
            regimes,
            validation,
        )
        verdict = (
            "需核验；不构成可靠性评级" if request.lang == "zh" else "Unrated; verification required"
        )
        # Exclude indicator warm-up and the synthetic baseline from risk statistics.
        metrics = self._metrics(
            strategy_returns[start:],
            benchmark_returns[start:] if benchmark_returns is not None else None,
            trades,
        )
        narrative = self._fallback_narrative(checks, request.lang)
        narrative = await self._ai_narrative(request, metrics, checks, narrative)

        dates = dates[start - 1 :]
        strategy_returns = [0.0, *strategy_returns[start:]]
        benchmark_returns = (
            [0.0, *benchmark_returns[start:]] if benchmark_returns is not None else None
        )
        strategy_equity = _equity(strategy_returns)
        benchmark_equity = _equity(benchmark_returns) if benchmark_returns is not None else None
        stride = max(1, math.ceil(len(dates) / 160))
        curve = [
            EquityPoint(
                date=dates[i],
                strategy=round(strategy_equity[i], 2),
                benchmark=round(benchmark_equity[i], 2) if benchmark_equity is not None else None,
            )
            for i in range(0, len(dates), stride)
        ]
        if curve[-1].date != dates[-1]:
            curve.append(
                EquityPoint(
                    date=dates[-1],
                    strategy=round(strategy_equity[-1], 2),
                    benchmark=(
                        round(benchmark_equity[-1], 2) if benchmark_equity is not None else None
                    ),
                )
            )

        return ForensicsReport(
            run_id=f"qf_{uuid4().hex[:12]}",
            created_at=datetime.now(UTC).isoformat(),
            ticker=request.ticker.upper(),
            benchmark=request.benchmark.upper() if request.benchmark else None,
            period=request.period,
            strategy=request.strategy,
            strategy_label=self._strategy_label(request),
            data_start=dates[0],
            data_end=dates[-1],
            observation_count=len(dates) - 1,
            verdict=verdict,
            metrics=metrics,
            benchmark_return_pct=(
                _pct(_compound(benchmark_returns)) if benchmark_returns is not None else None
            ),
            checks=checks,
            sensitivity=sensitivity,
            cost_scenarios=costs,
            regimes=regimes,
            equity_curve=curve,
            narrative=narrative,
            validation=validation,
            methodology=[
                f"Source: {asset.source or 'unspecified'}; "
                f"price basis: {asset.price_basis or 'unspecified'}; "
                f"benchmark: {benchmark.source if benchmark else 'none'}; "
                f"benchmark price basis: {benchmark.price_basis if benchmark else 'none'}.",
                "信号使用前日及以前数据，在下一交易日收盘成交；新仓位从成交后计收益。"
                if request.lang == "zh"
                else "Prior-close signals execute at next close; exposure earns thereafter.",
                "预热期不计入绩效；夏普/Alpha 无风险利率假设为 0，年化按 252 个交易日。"
                "盈利日占比按非零收益日计算；换仓次数不是完整买卖笔数。"
                if request.lang == "zh"
                else "Warm-up excluded; rf=0; annualization uses 252 sessions/year. "
                "Win rate counts nonzero return days; turnover events are not round trips.",
                "成本按换仓扣除；主回测期末按市值计价，未平仓不扣假想卖出费。"
                "未模拟停牌、涨跌停、整手、成交量限制和冲击成本；未验证历史财报可知时间。"
                if request.lang == "zh"
                else "Turnover costs; terminal holdings marked, not liquidated. "
                "No suspension, price-limit, lot-size, liquidity, impact or filing-time model.",
                "市场状态为事后分组，不可作为实时信号；RSI 采用窗口简单平均涨跌幅。"
                if request.lang == "zh"
                else "Retrospective regimes; RSI uses simple window averages.",
            ],
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
        asset: MarketDataResponse, benchmark: MarketDataResponse | None
    ) -> tuple[list[date], list[float], list[float] | None]:
        def prices(response: MarketDataResponse) -> dict[date, float]:
            result: dict[date, float] = {}
            for point in response.data:
                if not math.isfinite(point.close) or point.close <= 0:
                    raise NoMarketDataError("History contains invalid closing prices.")
                if point.trade_date in result and result[point.trade_date] != point.close:
                    raise NoMarketDataError(
                        "History contains conflicting prices for the same date."
                    )
                result[point.trade_date] = point.close
            return result

        asset_map = prices(asset)
        if benchmark is None:
            dates = sorted(asset_map)
            return dates, [asset_map[d] for d in dates], None
        bench_map = prices(benchmark)
        if set(asset_map) - set(bench_map):
            raise NoMarketDataError(
                "Benchmark missing asset dates; use the same market or leave it blank."
            )
        dates = sorted(asset_map)
        return dates, [asset_map[d] for d in dates], [bench_map[d] for d in dates]

    @staticmethod
    def _metrics(
        strategy: Sequence[float], benchmark: Sequence[float] | None, trades: int
    ) -> PerformanceMetrics:
        volatility = _std(strategy) * math.sqrt(252)
        sharpe = None if volatility == 0 else _safe_mean(strategy) * 252 / volatility
        downside = math.sqrt(_safe_mean([min(r, 0) ** 2 for r in strategy]) * 252)
        sortino = _safe_mean(strategy) * 252 / downside if downside else None
        drawdown = _max_drawdown(strategy)
        calmar = _annualized(strategy) / abs(drawdown) if drawdown else None
        active_days = [item for item in strategy if item != 0]
        wins = sum(1 for item in active_days if item > 0)
        beta, alpha = _beta_alpha(strategy, benchmark) if benchmark is not None else (None, None)
        return PerformanceMetrics(
            total_return_pct=_pct(_compound(strategy)),
            annualized_return_pct=_pct(_annualized(strategy)),
            annualized_volatility_pct=_pct(volatility),
            sharpe_ratio=round(sharpe, 2) if sharpe is not None else None,
            sortino_ratio=round(sortino, 2) if sortino is not None else None,
            calmar_ratio=round(calmar, 2) if calmar is not None else None,
            max_drawdown_pct=_pct(drawdown),
            win_rate_pct=round(100 * wins / len(active_days), 2) if active_days else None,
            trade_count=trades,
            beta=round(beta, 2) if beta is not None else None,
            alpha_pct=_pct(alpha) if alpha is not None else None,
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

    @staticmethod
    def _walk_forward(
        request: ForensicsRequest, dates: Sequence[date], closes: Sequence[float]
    ) -> WalkForwardResult:
        """Expanding training only; each following block is flat-start, net of liquidation."""
        note = (
            "五组窗口仅在各折训练段选优，随后在未参与本折选参的区间测试；"
            "每折从空仓开始并扣期末平仓费。属于内部滚动留出，不是外部独立验证；"
            "若已看过全部历史来选择策略或阈值，仍有选择偏差。"
            if request.lang == "zh"
            else "Five window pairs selected on expanding training data only; each following block "
            "starts flat and includes terminal liquidation costs. Internal holdout, not external "
            "validation; prior full-history strategy/threshold selection still introduces bias."
        )
        candidates = sorted(
            {
                (
                    max(3, round(request.fast_window * r)),
                    max(max(3, round(request.fast_window * r)) + 5, round(request.slow_window * r)),
                )
                for r in (0.8, 0.9, 1.0, 1.1, 1.2)
            }
        )
        warmup = max(slow for _, slow in candidates)
        split = max(warmup + 40, int(len(closes) * 0.6))
        if len(closes) - split < 60:
            return WalkForwardResult(
                note=note
                + (
                    " 历史不足：至少需要三个 20 日留出区间。"
                    if request.lang == "zh"
                    else " Insufficient history for three 20-session blocks."
                )
            )
        folds, all_returns = [], []
        edges = [split + (len(closes) - split) * i // 3 for i in range(4)]
        for start, stop in zip(edges, edges[1:], strict=False):

            def training_return(pair: tuple[int, int], train_end: int = start) -> float:
                signals = _signals_for_request(
                    closes[:train_end], request, fast=pair[0], slow=pair[1]
                )
                # Same evaluation start for every candidate.
                signals[:warmup] = [0.0] * warmup
                signals[-1] = 0.0
                returns, _ = _strategy_returns(
                    closes[:train_end], signals, request.transaction_cost_bps
                )
                return _compound(returns[warmup:])

            fast, slow = max(candidates, key=training_return)
            signals = _signals_for_request(closes[:stop], request, fast=fast, slow=slow)
            signals[:start] = [0.0] * start
            signals[-1] = 0.0
            returns, trades = _strategy_returns(
                closes[:stop], signals, request.transaction_cost_bps
            )
            returns = returns[start:]
            all_returns.extend(returns)
            folds.append(
                ValidationFold(
                    train_end=dates[start - 1],
                    test_start=dates[start],
                    test_end=dates[stop - 1],
                    fast_window=fast,
                    slow_window=slow,
                    total_return_pct=_pct(_compound(returns)),
                    max_drawdown_pct=_pct(_max_drawdown(returns)),
                    trade_count=trades,
                )
            )
        return WalkForwardResult(
            folds=folds,
            total_return_pct=_pct(_compound(all_returns)),
            note=note,
        )

    def _checks(
        self,
        request: ForensicsRequest,
        closes: Sequence[float],
        strategy: Sequence[float],
        benchmark: Sequence[float] | None,
        sensitivity: Sequence[SensitivityPoint],
        costs: Sequence[CostScenario],
        regimes: Sequence[RegimeResult],
        validation: WalkForwardResult,
    ) -> list[AuditCheck]:
        def text(zh: str, en: str) -> str:
            return zh if request.lang == "zh" else en

        # Report observations, not hand-tuned probabilities or investability ratings.
        signals = _signals_for_request(closes, request)
        prefix = len(closes) // 2
        stable = signals[:prefix] == _signals_for_request(closes[:prefix], request)
        checks = [
            AuditCheck(
                key="leakage",
                title=text("信号时序", "Signal timing"),
                status=AuditStatus.PASS if stable else AuditStatus.FAIL,
                finding=text(
                    "截断未来数据后，既有信号保持一致。" if stable else "信号时序检查失败。",
                    "Prefix signals unchanged." if stable else "Prefix test failed.",
                ),
                evidence=text(
                    "仅验证价格信号前缀不变性，不证明所有数据不存在前视偏差。",
                    "Price-prefix invariance only; not proof of all-data leakage safety.",
                ),
            ),
            AuditCheck(
                key="overfit",
                title=text("滚动留出验证", "Walk-forward holdout"),
                status=AuditStatus.WARNING,
                finding=text(
                    f"完成 {len(validation.folds)} 折；留出累计收益 "
                    + (
                        f"{validation.total_return_pct:+.2f}%。"
                        if validation.total_return_pct is not None
                        else "不可用。"
                    ),
                    f"{len(validation.folds)} folds; net return: {validation.total_return_pct}%.",
                ),
                evidence=validation.note,
            ),
            AuditCheck(
                key="sensitivity",
                title=text("参数敏感度", "Parameter sensitivity"),
                status=AuditStatus.WARNING,
                finding=text(
                    "同时扰动两个窗口；不覆盖全部阈值或策略选择。",
                    "Both windows perturbed; thresholds/strategy selection not covered.",
                ),
                evidence=text("五组参数累计收益：", "Five candidate returns: ")
                + " / ".join(f"{p.total_return_pct:+.2f}%" for p in sensitivity),
            ),
            AuditCheck(
                key="cost",
                title=text("成本压力", "Cost stress"),
                status=AuditStatus.WARNING,
                finding=text(
                    "简化换仓成本测试，不能代表真实可成交性。",
                    "Turnover cost stress, not proof of executable returns.",
                ),
                evidence=" / ".join(
                    f"{p.cost_bps:g}bps: {p.total_return_pct:+.2f}%" for p in costs
                ),
            ),
            AuditCheck(
                key="regime",
                title=text("事后市场分组", "Retrospective regimes"),
                status=AuditStatus.WARNING,
                finding=text(
                    "分组收益用于描述，短样本年化不代表全年可实现收益。",
                    "Descriptive groups; short-group annualization is not a forecast.",
                ),
                evidence=" / ".join(
                    f"{p.regime}: {p.trading_days}d, {p.annualized_return_pct:+.2f}%"
                    for p in regimes
                ),
            ),
        ]
        if benchmark is not None:
            beta, alpha = _beta_alpha(
                strategy[request.slow_window :], benchmark[request.slow_window :]
            )
            checks.append(
                AuditCheck(
                    key="attribution",
                    title=text("单基准归因", "Single-benchmark attribution"),
                    status=AuditStatus.WARNING,
                    finding=text(
                        "描述性回归，未检验统计显著性；不等于已发现超额收益能力。",
                        "Descriptive regression without significance testing; not proven skill.",
                    ),
                    evidence=(
                        f"Beta {beta:.2f}; alpha {_pct(alpha):+.2f}%/year; rf=0."
                        if beta is not None and alpha is not None
                        else text(
                            "基准方差为零或样本不足，无法估计。",
                            "Zero benchmark variance or insufficient observations.",
                        )
                    ),
                )
            )
        return checks

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
    def _fallback_narrative(checks: Sequence[AuditCheck], lang: str) -> ForensicsNarrative:
        if lang == "zh":
            return ForensicsNarrative(
                summary="已生成可复核的历史评估，不提供未经校准的可信度评分。",
                primary_cause=next(check.finding for check in checks if check.key == "overfit"),
                repair_action="优先核对留出区间、真实成交约束和数据口径；不要只按历史收益选策略。",
            )
        return ForensicsNarrative(
            summary="Reproducible historical diagnostics; no uncalibrated confidence score.",
            primary_cause=next(check.finding for check in checks if check.key == "overfit"),
            repair_action="Review holdouts, execution constraints and price basis.",
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
        try:
            response = await self._llm.chat(
                [
                    LLMMessage(
                        role="system",
                        content=(
                            "You explain a completed quantitative strategy audit. "
                            "Never alter numbers, promise returns, or add facts. "
                            "Return JSON only with three short strings: "
                            "summary, primary_cause, repair_action. Use " + language + "."
                        ),
                    ),
                    LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
                ],
                temperature=0.1,
                max_tokens=320,
            )
        except Exception:
            logger.info("Quant narrative unavailable; returning deterministic audit narrative.")
            return fallback
        content = response.message.content.strip()
        if not content:
            return fallback
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict) or not all(
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
