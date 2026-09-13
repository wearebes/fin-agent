"""Annual statement arithmetic. No provider calls, model numbers or investment scores."""

from __future__ import annotations

import math
from collections import defaultdict

from fin_agent.domain.reports import ReportChart, ReportData, ReportMetric, ReportSeries
from fin_agent.domain.types import FinancialStatementResponse


def append_financial_analysis(
    responses: list[FinancialStatementResponse], output: ReportData, lang: str = "zh"
) -> None:
    def text(zh: str, en: str) -> str:
        return en if lang == "en" else zh

    # A fiscal-year label alone cannot justify merging data from different vendors/currencies.
    groups = defaultdict(dict)
    conflicts = set()
    for response in responses:
        for row in response.data:
            if row.fiscal_quarter is not None:
                continue
            group = (response.ticker, response.source, response.currency)
            key = (row.fiscal_year, response.statement_type.value)
            existing = groups[group].get(key)
            if existing is not None and existing != row:
                conflicts.add((group, key))
            groups[group][key] = row
    for group, key in conflicts:
        del groups[group][key]
        output.gaps.append(
            text(
                f"{group[0]} {key[0]} 存在冲突版本，已排除该年度报表的指标计算。",
                f"{group[0]} {key[0]} conflicting versions excluded from ratio calculations.",
            )
        )

    labels = [
        (
            "revenue_growth",
            "收入同比",
            "Revenue growth",
            "%",
            "(revenue / prior revenue - 1) × 100",
        ),
        ("margin", "净利率", "Net margin", "%", "net income / revenue × 100"),
        ("debt_ratio", "资产负债率", "Liabilities / assets", "%", "liabilities / assets × 100"),
        ("roa", "总资产净利率", "ROA", "%", "net income / average assets × 100"),
        ("roe", "权益净利率", "ROE", "%", "net income / average equity × 100"),
        (
            "cash_conversion",
            "经营现金流/净利润",
            "Cash / earnings",
            "x",
            "operating cash / net income",
        ),
        ("turnover", "总资产周转率", "Asset turnover", "x", "revenue / average assets"),
        ("leverage", "权益乘数", "Equity multiplier", "x", "average assets / average equity"),
    ]
    peer_margins = defaultdict(list)
    for (ticker, source, currency), records in sorted(
        groups.items(), key=lambda pair: str(pair[0])
    ):
        years = sorted({year for year, _ in records})
        if not years:
            continue
        values = {key: [] for key, *_ in labels}
        for year in years:
            income = records.get((year, "income_statement"))
            balance = records.get((year, "balance_sheet"))
            cash = records.get((year, "cash_flow"))
            prior_income = records.get((year - 1, "income_statement"))
            prior_balance = records.get((year - 1, "balance_sheet"))

            def number(row, field):
                value = getattr(row, field, None)
                return value if value is not None and math.isfinite(value) else None

            def ratio(numerator, denominator, scale=1):
                if numerator is None or denominator is None or denominator <= 0:
                    return None
                result = numerator / denominator * scale
                return result if math.isfinite(result) else None

            def comparable(*rows, source=source, currency=currency):
                return (
                    bool(source and currency and all(rows))
                    and len({row.period_end for row in rows}) == 1
                    and rows[0].period_end is not None
                )

            def annual_pair(current, previous):
                if current is None or previous is None:
                    return False
                if current.period_end is None or previous.period_end is None:
                    return False
                return 350 <= (current.period_end - previous.period_end).days <= 380

            def balanced(row):
                a, liabilities, e = (
                    number(row, f) for f in ("total_assets", "total_liabilities", "total_equity")
                )
                return all(v is not None for v in (a, liabilities, e)) and abs(
                    a - liabilities - e
                ) <= max(1, abs(a) * 0.001)

            revenue, profit = number(income, "total_revenue"), number(income, "net_income")
            assets, equity = number(balance, "total_assets"), number(balance, "total_equity")
            avg_assets = avg_equity = None
            if comparable(income, balance) and annual_pair(balance, prior_balance):
                if balanced(balance) and balanced(prior_balance):
                    if assets > 0 and number(prior_balance, "total_assets") > 0:
                        avg_assets = (assets + prior_balance.total_assets) / 2
                    if equity > 0 and number(prior_balance, "total_equity") > 0:
                        avg_equity = (equity + prior_balance.total_equity) / 2
                else:
                    output.gaps.append(
                        text(
                            f"{ticker} {year} 资产≠负债+权益或字段缺失；未生成跨表 ROA/ROE。",
                            f"{ticker} {year} balance identity not verified; ROA/ROE omitted.",
                        )
                    )
            growth = ratio(revenue, number(prior_income, "total_revenue"), 100)
            current = {
                "revenue_growth": growth - 100
                if growth is not None and annual_pair(income, prior_income)
                else None,
                "margin": ratio(profit, revenue, 100),
                "debt_ratio": ratio(number(balance, "total_liabilities"), assets, 100),
                "roa": ratio(profit, avg_assets, 100),
                "roe": ratio(profit, avg_equity, 100),
                "cash_conversion": ratio(number(cash, "operating_cash_flow"), profit)
                if comparable(income, cash)
                else None,
                "turnover": ratio(revenue, avg_assets),
                "leverage": ratio(avg_assets, avg_equity),
            }
            for key in values:
                values[key].append(current[key])
            if year == years[-1]:
                for key, zh, en, unit, formula in labels:
                    value = current[key]
                    if value is None:
                        continue
                    context = f"FY {year}; {formula}; {source or 'source unspecified'}; "
                    context += f"{currency or 'currency unspecified'}; period end: "
                    context += str((income or balance or cash).period_end)
                    label = f"{ticker} {text(zh, en)}"
                    output.metrics.append(
                        ReportMetric(
                            label=label,
                            value=round(value, 4),
                            unit=unit,
                            context=context,
                        )
                    )
                    output.summary.append(f"{label}: {value:.4f}{unit} [{context}]")
                if current["margin"] is not None and income.period_end:
                    peer_margins[income.period_end].append((ticker, current["margin"], source))
        for key, zh, en, unit, formula in labels:
            if sum(v is not None for v in values[key]) < 2:
                continue
            output.charts.append(
                ReportChart(
                    title=f"{ticker} {text(zh, en)}",
                    kind="line",
                    unit=unit,
                    labels=[str(y) for y in years],
                    series=[ReportSeries(name=text(zh, en), values=values[key])],
                    source=source or "unspecified",
                    note=f"{formula}; "
                    + text(
                        "仅年度数据；跨表指标要求来源、币种和期末日期一致。",
                        "Annual ratios; matching source, currency and date required.",
                    ),
                )
            )
        output.gaps.append(
            text(
                f"{ticker}：缺失字段、非正分母或不可比期间不计算相关比率；"
                "ROE 为报表权益口径代理值，非强制归母口径；行业适用性需复核。"
                "未验证历史时点可知版本，不能将最新财报直接用于历史选股。",
                f"{ticker}: missing fields, invalid denominators or periods omitted. "
                "ROE uses reported equity; industry and parent-only scope need review. "
                "No historical version validation; do not backtest with latest financials.",
            )
        )
    for period_end, peers in peer_margins.items():
        if len({p[0] for p in peers}) != len(peers) or len(peers) < 2:
            continue
        output.charts.append(
            ReportChart(
                title=text("同期标的净利率比较", "Same-period net margins"),
                kind="bar",
                unit="%",
                labels=[p[0] for p in peers],
                series=[ReportSeries(name=str(period_end), values=[p[1] for p in peers])],
                source="; ".join(f"{p[0]}: {p[2]}" for p in peers),
                note=text(
                    "仅比较已取数且期末日期相同的标的，未自动认定为同行。",
                    "Matching period ends; industry comparability not verified.",
                ),
            )
        )
