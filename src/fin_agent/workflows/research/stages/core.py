from __future__ import annotations

import json
import logging
from uuid import uuid4

from fin_agent.domain.types import EvidenceItem, LLMMessage, TraceRecord
from fin_agent.workflows.research.context import (
    FinancialsPlanItem,
    MarketDataPlanItem,
    ResearchContext,
    RetrievalPlan,
    SearchPlanItem,
)
from fin_agent.workflows.research.stages import StageDeps

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are a research planning assistant for financial analysis.
Given a research question and optional ticker, produce a JSON retrieval plan.

The JSON must have exactly these keys:
- "search_queries": list of {{"query": str, "max_results": int}}
- "market_data": list of {{"ticker": str, \
"asset_type": "stock|etf|crypto|index|forex|bond|commodity", \
"frequency": "daily|weekly|monthly", "period": str}}
- "financials": list of {{"ticker": str, \
"statement_type": "income_statement|balance_sheet|cash_flow", \
"frequency": "yearly|quarterly"}}
- "fetch_company_info_tickers": list of ticker strings
- "fetch_analyst_data_tickers": list of ticker strings
- "fetch_crypto_tickers": list of crypto ticker strings (e.g. BTC-USD)

Be specific and targeted. Limit searches to 3-5 queries.
Only include items relevant to the question.
Respond with ONLY the JSON object, no markdown fences.
"""


async def intake(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    ctx = ctx.model_copy(update={"run_id": uuid4().hex})
    ctx.trace.append(
        TraceRecord(
            stage="intake",
            detail=f"Accepted research request: {ctx.request.question}"
            + (f" (ticker={ctx.request.ticker})" if ctx.request.ticker else ""),
        )
    )
    return ctx


async def plan(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    user_content = f"Research question: {ctx.request.question}"
    if ctx.request.ticker:
        user_content += f"\nTicker: {ctx.request.ticker}"

    messages = [
        LLMMessage(role="system", content=PLAN_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    try:
        resp = await deps.llm.chat(messages, temperature=0.2, max_tokens=1024)
        plan_text = resp.message.content.strip()
        plan_data = json.loads(plan_text)
        retrieval_plan = RetrievalPlan(
            search_queries=[
                SearchPlanItem(**q) for q in plan_data.get("search_queries", [])
            ],
            market_data=[
                MarketDataPlanItem(**m) for m in plan_data.get("market_data", [])
            ],
            financials=[
                FinancialsPlanItem(**f) for f in plan_data.get("financials", [])
            ],
            fetch_company_info_tickers=plan_data.get(
                "fetch_company_info_tickers", []
            ),
            fetch_analyst_data_tickers=plan_data.get(
                "fetch_analyst_data_tickers", []
            ),
            fetch_crypto_tickers=plan_data.get("fetch_crypto_tickers", []),
        )
    except Exception:
        logger.exception("plan stage LLM call or parse failed, using fallback plan")
        retrieval_plan = _fallback_plan(ctx)

    ctx = ctx.model_copy(update={"plan": retrieval_plan})
    ctx.trace.append(
        TraceRecord(
            stage="plan",
            detail=(
                f"Generated retrieval plan: "
                f"{len(retrieval_plan.search_queries)} searches, "
                f"{len(retrieval_plan.market_data)} market data, "
                f"{len(retrieval_plan.financials)} financials"
            ),
        )
    )
    return ctx


def _fallback_plan(ctx: ResearchContext) -> RetrievalPlan:
    plan = RetrievalPlan(
        search_queries=[SearchPlanItem(query=ctx.request.question, max_results=5)]
    )
    if ctx.request.ticker:
        plan.market_data.append(
            MarketDataPlanItem(ticker=ctx.request.ticker, period="1y")
        )
        plan.fetch_company_info_tickers.append(ctx.request.ticker)
        plan.fetch_analyst_data_tickers.append(ctx.request.ticker)
    return plan


async def retrieve(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    plan = ctx.plan
    new_evidence: list[EvidenceItem] = []

    for item in plan.search_queries:
        try:
            resp = deps.search.search(item.query, max_results=item.max_results)
            for r in resp.results:
                new_evidence.append(
                    EvidenceItem(
                        source=f"search:{item.query}",
                        summary=f"[{r.title}]({r.url})"
                        + (f" — {r.text[:500]}" if r.text else ""),
                    )
                )
        except Exception:
            logger.exception("retrieve: search failed for query=%s", item.query)

    for md_item in plan.market_data:
        try:
            md_resp = deps.market_data.get_market_data(
                md_item.ticker,
                md_item.asset_type,
                frequency=md_item.frequency,
                period=md_item.period,
            )
            if md_resp.data:
                latest = md_resp.data[-1]
                new_evidence.append(
                    EvidenceItem(
                        source=f"market_data:{md_item.ticker}",
                        summary=(
                            f"{md_item.ticker} latest ({latest.trade_date}): "
                            f"close={latest.close}, volume={latest.volume}"
                        ),
                    )
                )
        except Exception:
            logger.exception(
                "retrieve: market_data failed for ticker=%s", md_item.ticker
            )

    for fin_item in plan.financials:
        try:
            fin_resp = deps.market_data.get_financials(
                fin_item.ticker, fin_item.statement_type, frequency=fin_item.frequency
            )
            if fin_resp.data:
                new_evidence.append(
                    EvidenceItem(
                        source=(
                            f"financials:{fin_item.ticker}"
                            f":{fin_item.statement_type.value}"
                        ),
                        summary=(
                            f"{fin_item.ticker} {fin_item.statement_type.value}: "
                            f"{len(fin_resp.data)} records, "
                            f"latest FY={fin_resp.data[-1].fiscal_year}"
                        ),
                    )
                )
        except Exception:
            logger.exception(
                "retrieve: financials failed for ticker=%s", fin_item.ticker
            )

    for ticker in plan.fetch_company_info_tickers:
        try:
            info = deps.market_data.get_company_info(ticker)
            new_evidence.append(
                EvidenceItem(
                    source=f"company_info:{ticker}",
                    summary=(
                        f"{info.name or ticker} | Sector: {info.sector} | "
                        f"Market Cap: {info.market_cap} | {info.description or ''}"
                    ),
                )
            )
        except Exception:
            logger.exception("retrieve: company_info failed for ticker=%s", ticker)

    for ticker in plan.fetch_analyst_data_tickers:
        try:
            analyst_resp = deps.market_data.get_analyst_data(ticker)
            recs = analyst_resp.recommendations[:5]
            rec_summary = "; ".join(
                f"{r.firm}: {r.rating}" for r in recs if r.firm and r.rating
            )
            new_evidence.append(
                EvidenceItem(
                    source=f"analyst:{ticker}",
                    summary=f"Analyst recommendations: {rec_summary or 'none'}",
                )
            )
        except Exception:
            logger.exception("retrieve: analyst_data failed for ticker=%s", ticker)

    for ticker in plan.fetch_crypto_tickers:
        try:
            crypto_resp = deps.market_data.get_crypto_data(ticker)
            if crypto_resp.data:
                crypto_latest = crypto_resp.data[-1]
                new_evidence.append(
                    EvidenceItem(
                        source=f"crypto:{ticker}",
                        summary=(
                            f"{ticker} latest ({crypto_latest.trade_date})"
                            f": close={crypto_latest.close}"
                        ),
                    )
                )
        except Exception:
            logger.exception("retrieve: crypto_data failed for ticker=%s", ticker)

    limited = new_evidence[: deps.config.evidence_limit]
    ctx = ctx.model_copy(update={"evidence": ctx.evidence + limited})
    ctx.trace.append(
        TraceRecord(
            stage="retrieve",
            detail=f"Collected {len(limited)} evidence items from retrieval plan",
        )
    )
    return ctx
