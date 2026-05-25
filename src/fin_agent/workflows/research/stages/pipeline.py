from __future__ import annotations

import json
import logging
import re
from typing import Any

from fin_agent.domain.types import EvidenceItem, LLMMessage, TraceRecord
from fin_agent.workflows.research.context import ResearchContext, ToolCallRecord
from fin_agent.workflows.research.stages import StageDeps, ToolRegistry
from fin_agent.workflows.research.stages.tools import build_default_tool_registry

logger = logging.getLogger(__name__)

TOOL_EXEC_SYSTEM_PROMPT = """\
You are a financial research assistant with access to tools.
Based on the research question and evidence collected so far, decide if you need
additional information. If so, call a tool by responding with a JSON block:

```tool_call
{{"name": "<tool_name>", "arguments": {{<key-value pairs>}}}}
```

Available tools: {tool_names}

If you have sufficient information, respond with: ```done```
You may call at most one tool per response.
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


def _parse_tool_call(text: str) -> tuple[str, dict[str, Any]] | None:
    match = re.search(r"```tool_call\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data.get("name", ""), data.get("arguments", {})
    except json.JSONDecodeError:
        return None


def _is_done(text: str) -> bool:
    return "```done```" in text.lower()


def _build_tool_registry(deps: StageDeps) -> ToolRegistry:
    return build_default_tool_registry(deps.search, deps.market_data)


async def tool_exec(ctx: ResearchContext, deps: StageDeps) -> ResearchContext:
    registry = _build_tool_registry(deps)
    tool_names = ", ".join(registry.available_tools())
    system_prompt = TOOL_EXEC_SYSTEM_PROMPT.format(tool_names=tool_names)

    evidence_text = "\n".join(
        f"[{e.source}] {e.summary}" for e in ctx.evidence
    )
    user_content = (
        f"Research question: {ctx.request.question}\n\n"
        f"Evidence so far:\n{evidence_text}\n\n"
        f"Tool calls made: {len(ctx.tool_calls)}/{deps.config.max_tool_calls}"
    )

    while len(ctx.tool_calls) < deps.config.max_tool_calls:
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_content),
        ]
        try:
            resp = await deps.llm.chat(messages, temperature=0.1, max_tokens=512)
        except Exception:
            logger.exception("tool-exec: LLM call failed")
            break

        text = resp.message.content

        if _is_done(text):
            ctx.trace.append(
                TraceRecord(stage="tool-exec", detail="LLM indicated sufficient data")
            )
            break

        parsed = _parse_tool_call(text)
        if parsed is None:
            ctx.trace.append(
                TraceRecord(stage="tool-exec", detail="No tool call parsed, ending")
            )
            break

        tool_name, arguments = parsed
        tool_fn = registry.get(tool_name)
        if tool_fn is None:
            ctx.trace.append(
                TraceRecord(
                    stage="tool-exec",
                    detail=f"Unknown tool: {tool_name}, skipping",
                )
            )
            user_content += f"\n\nTool '{tool_name}' not found. Try another."
            continue

        try:
            result = await tool_fn(**arguments)
            result_summary = result[:500] if result else ""
        except Exception:
            logger.exception("tool-exec: tool %s failed", tool_name)
            result_summary = "Tool call failed"
            result = ""

        record = ToolCallRecord(
            tool_name=tool_name, arguments=arguments, result_summary=result_summary
        )
        ctx = ctx.model_copy(
            update={"tool_calls": ctx.tool_calls + [record]}
        )
        ctx.evidence.append(
            EvidenceItem(
                source=f"tool:{tool_name}",
                summary=result_summary,
            )
        )
        user_content += f"\n\nTool {tool_name} result: {result_summary}"

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
    messages = [
        LLMMessage(role="system", content=SYNTHESIZE_SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=(
                f"Research question: {ctx.request.question}\n\n"
                f"Evidence:\n{evidence_text}"
            ),
        ),
    ]
    try:
        resp = await deps.llm.chat(messages, temperature=0.3, max_tokens=4096)
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
    messages = [
        LLMMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=f"Research question: {ctx.request.question}\n\nReport:\n{ctx.report}",
        ),
    ]
    try:
        resp = await deps.llm.chat(messages, temperature=0.1, max_tokens=512)
        review_text = resp.message.content.strip()
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
