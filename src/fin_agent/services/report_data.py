"""Reproducible figures from captured observations; no additional API calls.

Chart contract: daily prices and common-date comparisons use lines (>=8 dates).
Fiscal-year financial comparisons use bars from zero. Each figure keeps units,
source, date range and missing values. Model-generated numbers are never parsed.
"""

import math
from datetime import UTC, datetime
from statistics import stdev

from fin_agent.domain.reports import ReportChart, ReportData, ReportMetric, ReportSeries
from fin_agent.domain.types import FinancialStatementResponse, MarketDataResponse


def build_report_data(ctx) -> ReportData:
    def text(cn, en):
        return cn if ctx.request.lang != "en" else en

    output = ReportData(
        captured_at=ctx.metadata.get("captured_at", datetime.now(UTC).isoformat()),
        narrative="ai"
        if any(
            t.stage == "synthesize" and t.detail.startswith("Generated report") for t in ctx.trace
        )
        else "data_only",
    )
    markets, sources = {}, {}
    for raw in ctx.metadata.get("report_market", [])[:4]:
        response = MarketDataResponse.model_validate(raw)
        points = sorted(
            {
                p.trade_date: p for p in response.data if math.isfinite(p.close) and p.close > 0
            }.values(),
            key=lambda p: p.trade_date,
        )
        if len(points) < 8:
            continue
        ticker = response.ticker
        dates, closes = [str(p.trade_date) for p in points], [p.close for p in points]
        source = response.source or text("行情适配器（上游未标注）", "Market adapter")
        markets[ticker], sources[ticker] = dict(zip(dates, closes, strict=True)), source
        peak, drawdowns = closes[0], []
        for close in closes:
            peak = max(peak, close)
            drawdowns.append((close / peak - 1) * 100)
        changes = [b / a - 1 for a, b in zip(closes, closes[1:], strict=False)]
        period = f"{dates[0]} → {dates[-1]} · {len(dates)} " + text("个观测值", "observations")
        gain = (closes[-1] / closes[0] - 1) * 100
        for label, value in [
            (text("区间价格变动", "price change"), gain),
            (text("最大回撤", "max drawdown"), min(drawdowns)),
        ]:
            output.metrics.append(
                ReportMetric(
                    label=f"{ticker} {label}", value=round(value, 2), unit="%", context=period
                )
            )
        if response.frequency.value == "daily" and len(changes) > 1:
            output.metrics.append(
                ReportMetric(
                    label=f"{ticker} " + text("年化波动率", "annualized volatility"),
                    value=round(stdev(changes) * math.sqrt(252) * 100, 2),
                    unit="%",
                    context=text("日收益率样本标准差 × √252；", "Daily sample stdev × √252; ")
                    + period,
                )
            )
        output.summary.append(
            text(
                f"{ticker} 在 {dates[0]} 至 {dates[-1]} 价格变动 {gain:+.2f}%，"
                f"期间最大回撤 {min(drawdowns):.2f}%。",
                f"{ticker}: {gain:+.2f}% price change, {min(drawdowns):.2f}% max drawdown; "
                f"{dates[0]} to {dates[-1]}.",
            )
        )
        basis = response.price_basis or text("来源未提供复权口径", "Adjustment basis unspecified")
        # A focal instrument has price and drawdown charts; peers share a comparison chart.
        charts = [
            ReportChart(
                title=f"{ticker} " + text("历史收盘价", "historical close"),
                kind="line",
                unit=response.currency or text("报价单位未标注", "Quote units"),
                labels=dates,
                series=[ReportSeries(name=ticker, values=closes)],
                source=source,
                note=period + " · " + basis,
            ),
            ReportChart(
                title=f"{ticker} " + text("回撤走势", "drawdown"),
                kind="line",
                unit="%",
                labels=dates,
                series=[ReportSeries(name=text("回撤", "Drawdown"), values=drawdowns)],
                source=source,
                note=text("相对截至当日历史高点；", "Relative to running peak; ") + period,
            ),
        ]
        if not output.charts:
            output.charts.extend(charts)
        for label, value in [("PE TTM", points[-1].pe_ttm), ("PB", points[-1].pb)]:
            if value is not None and math.isfinite(value):
                output.metrics.append(
                    ReportMetric(
                        label=f"{ticker} {label}",
                        value=value,
                        unit=text("倍", "x"),
                        context=dates[-1],
                    )
                )
    if len(markets) >= 2:
        common = sorted(set.intersection(*(set(rows) for rows in markets.values())))
        if len(common) >= 8:
            output.charts.append(
                ReportChart(
                    title=text("同期价格表现比较", "Same-period price comparison"),
                    kind="line",
                    unit="%",
                    labels=common,
                    series=[
                        ReportSeries(
                            name=ticker,
                            values=[(rows[d] / rows[common[0]] - 1) * 100 for d in common],
                        )
                        for ticker, rows in markets.items()
                    ],
                    source="; ".join(f"{t}: {s}" for t, s in sources.items()),
                    note=text(
                        "共同交易日起点归零；未做汇率调整，非统一总回报口径。",
                        "Common dates; no FX adjustment or harmonized total return.",
                    ),
                )
            )
    for raw in ctx.metadata.get("report_financials", [])[:4]:
        response = FinancialStatementResponse.model_validate(raw)
        rows = sorted(
            [r for r in response.data if r.fiscal_quarter is None], key=lambda r: r.fiscal_year
        )
        rows = list({r.fiscal_year: r for r in rows}.values())
        series = [
            ReportSeries(
                name=text(cn, en),
                values=[
                    value if value is not None and math.isfinite(value) else None
                    for value in (getattr(r, key) for r in rows)
                ],
            )
            for key, cn, en in [
                ("total_revenue", "营业收入", "Revenue"),
                ("net_income", "净利润", "Net income"),
            ]
            if any(getattr(r, key) is not None for r in rows)
        ]
        if len(rows) >= 2 and series:
            output.charts.append(
                ReportChart(
                    title=f"{response.ticker} " + text("年度财务表现", "annual financials"),
                    kind="bar",
                    unit=response.currency
                    or text("原始报表单位（币种未提供）", "Original units (currency unspecified)"),
                    labels=[str(r.fiscal_year) for r in rows],
                    series=series,
                    source=response.source or text("财务适配器（上游未标注）", "Financial adapter"),
                    note=text(
                        "按财政年度；缺失值留空，不补零。",
                        "Fiscal years; missing values remain gaps.",
                    ),
                )
            )
    for missing, cn, en in [
        (
            not markets,
            "没有足够的行情观测值，未生成走势或风险指标。",
            "Insufficient price observations.",
        ),
        (
            not any(c.kind == "bar" for c in output.charts),
            "未取得至少两年的可用财务数据。",
            "Two years of financials unavailable.",
        ),
        (
            len(markets) < 2,
            "未取得可比标的的同期数据，未生成同业/基准比较。",
            "Comparable instrument data unavailable.",
        ),
        (
            not any("PE TTM" in m.label or "PB" in m.label for m in output.metrics),
            "来源未提供可核验的 PE/PB，未展示估值倍数。",
            "Verified PE/PB multiples unavailable.",
        ),
    ]:
        if missing:
            output.gaps.append(text(cn, en))
    return output
