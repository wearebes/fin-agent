"""Hand-calculated accounting identities and execution/holdout regressions."""

from datetime import date

import pytest
from test_forensics import FakeMarketData, _series

from fin_agent.domain.constants import FinancialStatementType as Statement
from fin_agent.domain.forensics import ForensicsRequest
from fin_agent.domain.reports import ReportData
from fin_agent.domain.types import FinancialStatementRecord, FinancialStatementResponse
from fin_agent.services.financial_analysis import append_financial_analysis
from fin_agent.services.forensics import (
    ForensicsService,
    NoMarketDataError,
    _compound,
    _rsi,
    _strategy_returns,
)


def statements():
    fields = {
        Statement.INCOME_STATEMENT: [
            {"total_revenue": 100, "net_income": 10},
            {"total_revenue": 120, "net_income": 18},
        ],
        Statement.BALANCE_SHEET: [
            {"total_assets": 200, "total_liabilities": 100, "total_equity": 100},
            {"total_assets": 300, "total_liabilities": 150, "total_equity": 150},
        ],
        Statement.CASH_FLOW: [{"operating_cash_flow": 15}, {"operating_cash_flow": 27}],
    }
    return [
        FinancialStatementResponse(
            ticker="TEST",
            statement_type=kind,
            source="Annual filing fixture",
            currency="CNY",
            data=[
                FinancialStatementRecord(
                    ticker="TEST",
                    statement_type=kind,
                    fiscal_year=2023 + i,
                    period_end=date(2023 + i, 12, 31),
                    **row,
                )
                for i, row in enumerate(rows)
            ],
        )
        for kind, rows in fields.items()
    ]


def analyze(rows):
    output = ReportData(captured_at="2025-05-01", narrative="data_only")
    append_financial_analysis(rows, output, "en")
    return output, {m.label.removeprefix("TEST "): m.value for m in output.metrics}


def test_annual_metrics_match_hand_calculation_and_dupont_identity():
    output, metrics = analyze(statements())
    assert metrics["Revenue growth"] == 20
    assert metrics["Net margin"] == 15
    assert metrics["Liabilities / assets"] == 50
    assert metrics["ROA"] == 7.2  # 18 / average(200, 300)
    assert metrics["ROE"] == 14.4  # 18 / average(100, 150)
    assert metrics["Cash / earnings"] == 1.5
    assert metrics["Asset turnover"] == 0.48
    assert metrics["Equity multiplier"] == 2
    assert metrics["Net margin"] * metrics["Asset turnover"] * metrics[
        "Equity multiplier"
    ] == pytest.approx(14.4)
    assert all("Annual filing fixture" in m.context for m in output.metrics)


@pytest.mark.parametrize("change", ["currency", "source", "period", "equity", "prior"])
def test_incompatible_statements_do_not_produce_roe(change):
    rows = statements()
    balance = rows[1]
    if change == "currency":
        balance.currency = "USD"
    elif change == "source":
        balance.source = "Different vendor"
    elif change == "period":
        balance.data[-1].period_end = date(2024, 9, 30)
    elif change == "equity":
        balance.data[-1].total_equity = -50
    else:
        balance.data.pop(0)
    _, metrics = analyze(rows)
    assert "ROE" not in metrics


def test_conflicting_versions_and_loss_denominators_are_not_hidden():
    rows = statements()
    duplicate = rows[0].model_copy(deep=True)
    duplicate.data[-1].net_income = 90
    output, metrics = analyze([*rows, duplicate])
    assert any("conflicting" in gap for gap in output.gaps)
    assert "ROE" not in metrics
    rows[0].data[-1].net_income = -18
    rows[2].data[-1].operating_cash_flow = -27
    _, metrics = analyze(rows)
    assert metrics["Net margin"] == -15
    assert "Cash / earnings" not in metrics  # No misleading positive ratio of two losses.


def test_next_close_execution_does_not_capture_pre_fill_jump_and_charges_both_sides():
    returns, trades = _strategy_returns([100, 200, 300, 150], [0, 1, 1, 0], 100)
    assert returns == pytest.approx([0, -0.01, 0.5, -0.505])
    assert trades == 2
    assert _compound(returns) == pytest.approx(0.99 * 1.5 * 0.495 - 1)
    assert _rsi([100] * 30, 25, 14) == 50


def test_walk_forward_parameter_choice_never_sees_its_test_prices():
    data = _series("TEST")
    dates, closes = [p.trade_date for p in data.data], [p.close for p in data.data]
    request = ForensicsRequest(ticker="TEST")
    baseline = ForensicsService._walk_forward(request, dates, closes)
    split = dates.index(baseline.folds[0].test_start)
    altered = [*closes[:split], *[v * 2 for v in closes[split:]]]
    changed = ForensicsService._walk_forward(request, dates, altered)
    assert len(baseline.folds) == 3
    assert (baseline.folds[0].fast_window, baseline.folds[0].slow_window) == (
        changed.folds[0].fast_window,
        changed.folds[0].slow_window,
    )
    for fold in baseline.folds:
        assert fold.train_end < fold.test_start <= fold.test_end
    assert _compound([f.total_return_pct / 100 for f in baseline.folds]) * 100 == pytest.approx(
        baseline.total_return_pct, abs=0.03
    )


def test_bad_prices_and_missing_benchmark_dates_are_explicit_errors():
    data, benchmark = _series("TEST"), _series("BASE")
    benchmark.data.pop(10)
    with pytest.raises(NoMarketDataError, match="missing asset dates"):
        ForensicsService._align(data, benchmark)
    data.data[3].close = float("inf")
    with pytest.raises(NoMarketDataError, match="invalid closing"):
        ForensicsService._align(data, None)


@pytest.mark.asyncio
async def test_public_report_excludes_warmup_and_does_not_emit_confidence_rating():
    report = await ForensicsService(FakeMarketData()).diagnose(ForensicsRequest(ticker="TEST"))
    assert report.observation_count == 520 - 60
    assert report.equity_curve[0].strategy == 100
    assert report.reliability_score is None
    assert all(c.score is None for c in report.checks)
    assert report.validation.folds


@pytest.mark.asyncio
async def test_synthesis_and_review_share_persisted_calculated_financial_evidence():
    from test_research_workflow import (
        REVIEW_RESPONSE,
        SYNTHESIZE_RESPONSE,
        _CapturingLLM,
        _make_deps,
    )

    from fin_agent.domain.types import EvidenceItem, ResearchRequest
    from fin_agent.workflows.research.config import ResearchWorkflowConfig
    from fin_agent.workflows.research.context import ResearchContext
    from fin_agent.workflows.research.stages.pipeline import review, synthesize

    ctx = ResearchContext(
        request=ResearchRequest(question="Explain profitability", ticker="TEST"),
        evidence=[EvidenceItem(source="annual filings", summary="Annual statements")],
        metadata={"report_financials": [s.model_dump(mode="json") for s in statements()]},
    )
    deps = _make_deps(ResearchWorkflowConfig())
    recorder = _CapturingLLM([SYNTHESIZE_RESPONSE, REVIEW_RESPONSE])
    deps.llm = recorder
    await synthesize(ctx, deps)
    evidence = next(e for e in ctx.evidence if e.source == "calculated:report-metrics")
    assert "14.4000" in evidence.summary
    await review(ctx, deps)
    assert any(e.source == "calculated:report-metrics" for e in ctx.evidence)
    assert len(recorder.calls) == 2
    assert all("14.4000" in messages[-1].content for messages in recorder.calls)


def test_degenerate_risk_metrics_are_unavailable_not_zero():
    metrics = ForensicsService._metrics([0.0] * 100, [0.0] * 100, 0)
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert metrics.calmar_ratio is None
    assert metrics.win_rate_pct is None
    assert metrics.beta is None
    assert metrics.alpha_pct is None


def test_downside_risk_matches_hand_calculation():
    metrics = ForensicsService._metrics([0.10, -0.05, 0.02, -0.01], None, 4)
    downside = ((0.05**2 + 0.01**2) / 4 * 252) ** 0.5
    assert metrics.sortino_ratio == round(0.015 * 252 / downside, 2)
    assert metrics.max_drawdown_pct == -5
    assert metrics.win_rate_pct == 50
