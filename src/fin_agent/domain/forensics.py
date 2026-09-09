"""Wire models for the Quant Forensics strategy audit."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class StrategyKind(StrEnum):
    MA_CROSS = "ma_cross"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    RSI_REVERSION = "rsi_reversion"
    MOMENTUM_TREND = "momentum_trend"
    BOLLINGER_REVERSION = "bollinger_reversion"
    CUSTOM = "custom"


class CustomSignalKind(StrEnum):
    MA_CROSS = "ma_cross"
    RSI = "rsi"
    MOMENTUM = "momentum"
    BOLLINGER = "bollinger"


class AuditStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ForensicsRequest(BaseModel):
    ticker: str = Field(default="SPY", min_length=1, max_length=24)
    benchmark: str | None = Field(default=None, min_length=1, max_length=24)
    period: str = Field(default="5y", pattern=r"^(1y|2y|5y|10y)$")
    strategy: StrategyKind = StrategyKind.MA_CROSS
    fast_window: int = Field(default=20, ge=3, le=120)
    slow_window: int = Field(default=60, ge=10, le=260)
    custom_signal: CustomSignalKind = CustomSignalKind.MA_CROSS
    entry_threshold: float = Field(default=0.2, ge=-100, le=100)
    exit_threshold: float = Field(default=0.0, ge=-100, le=100)
    strategy_name: str = Field(default="", max_length=40)
    transaction_cost_bps: float = Field(default=8.0, ge=0, le=100)
    lang: str = Field(default="zh", pattern=r"^(zh|en)$")

    @field_validator("benchmark", mode="before")
    @classmethod
    def normalize_optional_benchmark(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_windows(self) -> ForensicsRequest:
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        if self.strategy == StrategyKind.CUSTOM and self.custom_signal == CustomSignalKind.RSI:
            if not 0 < self.entry_threshold < self.exit_threshold < 100:
                raise ValueError(
                    "RSI custom thresholds must be between 0 and 100, with entry below exit"
                )
        return self


class EquityPoint(BaseModel):
    date: date
    strategy: float
    benchmark: float | None = None


class PerformanceMetrics(BaseModel):
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    beta: float | None = None
    alpha_pct: float | None = None


class AuditCheck(BaseModel):
    key: str
    title: str
    status: AuditStatus
    score: int = Field(ge=0, le=100)
    finding: str
    evidence: str


class SensitivityPoint(BaseModel):
    label: str
    fast_window: int
    slow_window: int
    total_return_pct: float


class CostScenario(BaseModel):
    cost_bps: float
    total_return_pct: float


class RegimeResult(BaseModel):
    regime: str
    trading_days: int
    annualized_return_pct: float


class ForensicsNarrative(BaseModel):
    summary: str
    primary_cause: str
    repair_action: str
    generated_by_ai: bool = False


class ForensicsReport(BaseModel):
    run_id: str
    created_at: str
    ticker: str
    benchmark: str | None = None
    period: str
    strategy: StrategyKind
    strategy_label: str
    data_start: date
    data_end: date
    observation_count: int
    reliability_score: int = Field(ge=0, le=100)
    verdict: str
    metrics: PerformanceMetrics
    benchmark_return_pct: float | None = None
    checks: list[AuditCheck]
    sensitivity: list[SensitivityPoint]
    cost_scenarios: list[CostScenario]
    regimes: list[RegimeResult]
    equity_curve: list[EquityPoint]
    narrative: ForensicsNarrative
    disclaimer: str
