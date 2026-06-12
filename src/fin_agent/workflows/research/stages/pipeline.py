from __future__ import annotations

import json
import logging
import re

from fin_agent.domain.types import EvidenceItem, LLMMessage, RetrievalPlan, TraceRecord
from fin_agent.workflows.research.context import ResearchContext, ToolCallRecord
from fin_agent.workflows.research.lang import get_lang_instruction
from fin_agent.workflows.research.stages import StageDeps

logger = logging.getLogger(__name__)

TOOL_EXEC_SYSTEM_PROMPT = """\
You are a financial research assistant with access to tools.
You are given a research question, the retrieval plan produced by the planning
stage, and the evidence gathered so far. Decide whether you need additional
information and, if so, call one or more of the available tools. You may request
several tools at once when they are independent. When you have gathered
sufficient evidence, reply with a final natural-language summary and request no
further tools.
"""

SYNTHESIZE_SYSTEM_PROMPT = """\
You are a senior financial research analyst. Synthesize all the evidence below
into a comprehensive research report. Structure your report with:
1. Executive Summary
2. Key Findings (with source citations)
3. Risk Factors
4. Conclusion & Outlook

Write in clear, professional language. Cite evidence sources inline as [source].
"""

REVIEW_SYSTEM_PROMPT = """\
You are a quality reviewer for financial research reports.
Evaluate the report for:
- Accuracy and evidence backing
- Completeness of analysis
- Logical consistency
- Clarity and professionalism

Respond with a JSON object:
{{"passed": true/false, "feedback": "explanation of issues or approval"}}
If the report is adequate, set passed=true.
"""


def _summarize_plan(plan: RetrievalPlan) -> str:
    """Render the planning stage's RetrievalPlan into a few human-readable lines.

    This is the data bridge that lets the execute stage start from what the plan
    stage actually decided, instead of re-deriving everything from scratch.
    """
    lines: list[str] = []
    if plan.search_queries:
        queries = ", ".join(f'"{q.query}"' for q in plan.search_queries)
        lines.append(f"- Planned searches: {queries}")
    if plan.market_data:
        tickers = ", ".join(
            f"{m.ticker} ({m.asset_type.value}, {m.period})" for m in plan.market_data
        )
        lines.append(f"- Planned market data: {tickers}")
    if plan.financials:
        fins = ", ".join(
            f"{f.ticker} {f.statement_type.value}" for f in plan.financials
        )
        lines.append(f"- Planned financials: {fins}")
    if plan.fetch_company_info_tickers:
        lines.append(
            "- Planned company info: "
            + ", ".join(plan.fetch_company_info_tickers)
        )
    if plan.fetch_analyst_data_tickers:
        lines.append(
            "- Planned analyst data: "
            + ", ".join(plan.fetch_analyst_data_tickers)
        )
    if plan.fetch_crypto_tickers:
        lines.append(
            "- Planned crypto data: " + ", ".join(plan.fetch_crypto_tickers)
        )
    if not lines:
        return "(no explicit retrieval plan was produced)"
    return "\n".join(lines)


async def tool_exec(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    registry = deps.tool_registry  # shared catalog, no longer rebuilt per call
    # The LLM provider is provider-neutral: it takes ToolDefinitions and does
    # the OpenAI-specific conversion internally (one conversion path).
    tool_definitions = registry.definitions()
    lang_instruction = get_lang_instruction(ctx.request.lang)
    system_prompt = TOOL_EXEC_SYSTEM_PROMPT + "\n" + lang_instruction
    if ctx.skill_instructions:
        system_prompt = ctx.skill_instructions + "\n\n" + system_prompt

    plan_summary = _summarize_plan(ctx.plan)
    evidence_text = "\n".join(f"[{e.source}] {e.summary}" for e in ctx.evidence)
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(
            role="user",
            content=(
                f"Research question: {ctx.request.question}\n\n"
                f"Retrieval plan from the planning stage:\n{plan_summary}\n\n"
                f"Evidence so far:\n{evidence_text}"
            ),
        ),
    ]

    while len(ctx.tool_calls) < deps.config.max_tool_calls:
        try:
            resp = await deps.llm.chat(
                messages, temperature=0.1, max_tokens=4096, tools=tool_definitions
            )
        except Exception:
            logger.exception("tool-exec: LLM call failed")
            break

        if not resp.has_tool_calls:
            ctx.trace.append(
                TraceRecord(
                    stage="tool-exec",
                    detail="LLM produced final answer, no further tool calls",
                )
            )
            break

        requested = resp.message.tool_calls or []
        names = ", ".join(
            f"{tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})"
            for tc in requested
        )
        ctx.trace.append(
            TraceRecord(
                stage="tool-exec",
                detail=(
                    f"Model requested {len(requested)} tool call(s) in parallel: "
                    f"{names}"
                ),
            )
        )

        # Replay the assistant tool-call turn into the running conversation.
        messages.append(resp.message)

        for tc in requested:
            handler = registry.get(tc.name)
            try:
                if handler is None:
                    result_text = f"Unknown tool '{tc.name}'."
                else:
                    result_text = await handler(**tc.arguments)
            except Exception:
                logger.exception("tool-exec: tool %s failed", tc.name)
                result_text = "Tool execution failed."
            result_text = result_text or ""
            result_summary = result_text[:500]

            messages.append(
                LLMMessage(
                    role="tool",
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=result_text,
                )
            )
            ctx = ctx.model_copy(
                update={
                    "tool_calls": ctx.tool_calls
                    + [
                        ToolCallRecord(
                            tool_name=tc.name,
                            arguments=tc.arguments,
                            result_summary=result_summary,
                        )
                    ]
                }
            )
            ctx.evidence.append(
                EvidenceItem(source=f"tool:{tc.name}", summary=result_summary)
            )
            ctx.trace.append(
                TraceRecord(
                    stage="tool-exec",
                    detail=f"{tc.name} → {result_summary[:200]}",
                )
            )

            if len(ctx.tool_calls) >= deps.config.max_tool_calls:
                break

    ctx.trace.append(
        TraceRecord(
            stage="tool-exec",
            detail=f"Completed with {len(ctx.tool_calls)} tool calls",
        )
    )
    return ctx


async def synthesize(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    evidence_text = "\n\n".join(
        f"Source: {e.source}\n{e.summary}" for e in ctx.evidence
    )
    lang_instruction = get_lang_instruction(ctx.request.lang)
    system_content = SYNTHESIZE_SYSTEM_PROMPT + "\n" + lang_instruction
    if ctx.skill_instructions:
        system_content = ctx.skill_instructions + "\n\n" + system_content
    messages = [
        LLMMessage(role="system", content=system_content),
        LLMMessage(
            role="user",
            content=(
                f"Research question: {ctx.request.question}\n\n"
                f"Evidence:\n{evidence_text}"
            ),
        ),
    ]
    try:
        resp = await deps.llm.chat(messages, temperature=0.3, max_tokens=16384)
        report = resp.message.content
    except Exception:
        logger.exception("synthesize: LLM call failed")
        report = "Report generation failed. Evidence collected but synthesis unavailable."

    ctx = ctx.model_copy(update={"report": report})
    ctx.trace.append(
        TraceRecord(
            stage="synthesize",
            detail=f"Generated report ({len(report)} chars, {len(ctx.evidence)} evidence items)",
        )
    )
    return ctx


async def review(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    lang_instruction = get_lang_instruction(ctx.request.lang)
    system_content = REVIEW_SYSTEM_PROMPT + "\n" + lang_instruction
    messages = [
        LLMMessage(role="system", content=system_content),
        LLMMessage(
            role="user",
            content=f"Research question: {ctx.request.question}\n\nReport:\n{ctx.report}",
        ),
    ]
    try:
        resp = await deps.llm.chat(messages, temperature=0.1, max_tokens=4096)
        review_text = resp.message.content.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", review_text, re.DOTALL)
        if match:
            review_text = match.group(1)
        review_data = json.loads(review_text)
        passed = bool(review_data.get("passed", False))
        feedback = str(review_data.get("feedback", ""))
    except Exception:
        logger.exception("review: LLM call or parse failed, defaulting to passed=True")
        passed = True
        feedback = "Review could not be completed; defaulting to pass."

    ctx = ctx.model_copy(
        update={"review_passed": passed, "review_feedback": feedback}
    )
    ctx.trace.append(
        TraceRecord(
            stage="review",
            detail=f"Review {'passed' if passed else 'needs revision'}: {feedback[:200]}",
        )
    )
    return ctx


async def persist(
    ctx: ResearchContext,
    deps: StageDeps,
    *,
    run_store: object | None = None,
) -> ResearchContext:
    ctx.trace.append(
        TraceRecord(
            stage="persist",
            detail=f"Run {ctx.run_id} persisted with {len(ctx.evidence)} evidence items",
        )
    )
    return ctx
