from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fin_agent.domain.types import ResearchProgress, TraceRecord
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext
from fin_agent.workflows.research.stages import StageDeps
from fin_agent.workflows.research.stages.core import intake, plan, retrieve
from fin_agent.workflows.research.stages.pipeline import (
    persist,
    review,
    synthesize,
    tool_exec,
)

logger = logging.getLogger(__name__)

StageCallable = Callable[[ResearchContext, StageDeps], Awaitable[ResearchContext]]
ProgressCallback = Callable[[ResearchProgress], None]

_STAGE_REGISTRY: dict[str, StageCallable] = {
    "intake": intake,
    "plan": plan,
    "retrieve": retrieve,
    "tool-exec": tool_exec,
    "synthesize": synthesize,
    "review": review,
    "persist": persist,
}


def build_stage_plan(config: ResearchWorkflowConfig) -> list[str]:
    stages = ["intake", "plan", "retrieve", "tool-exec", "synthesize"]
    if config.enable_review:
        stages.append("review")
    stages.append("persist")
    return stages


def build_resume_stages(config: ResearchWorkflowConfig) -> list[str]:
    """Stage list for resuming a paused plan-mode run (post-approval).

    Mirrors `build_stage_plan`'s tail — everything after "plan", which already
    ran before the run was paused in `awaiting_approval`.
    """
    stages = ["retrieve", "tool-exec", "synthesize"]
    if config.enable_review:
        stages.append("review")
    stages.append("persist")
    return stages


def register_stage(name: str, fn: StageCallable) -> None:
    _STAGE_REGISTRY[name] = fn


async def execute_workflow(
    ctx: ResearchContext,
    deps: StageDeps,
    *,
    stages: list[str] | None = None,
    extra_stage_kwargs: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> ResearchContext:
    stage_plan = stages if stages is not None else build_stage_plan(deps.config)
    for stage_name in stage_plan:
        if stage_name == "review" and "synthesize" in ctx.failed_stages:
            ctx.trace.append(TraceRecord(stage="review", detail="Skipped: synthesis unavailable"))
            if on_progress:
                on_progress(ResearchProgress(stage=stage_name, status="skipped"))
            continue
        fn = _STAGE_REGISTRY.get(stage_name)
        if fn is None:
            logger.warning("Unknown stage '%s', skipping", stage_name)
            continue
        logger.info("Executing stage: %s (run_id=%s)", stage_name, ctx.run_id)
        if on_progress:
            on_progress(ResearchProgress(stage=stage_name, status="running"))
        try:
            if stage_name == "persist" and extra_stage_kwargs:
                ctx = await fn(ctx, deps, **extra_stage_kwargs)
            else:
                ctx = await fn(ctx, deps)
        except Exception:
            logger.exception("Stage '%s' failed for run_id=%s", stage_name, ctx.run_id)
            ctx.fail(stage_name, "Stage failed with error")
        if on_progress:
            on_progress(
                ResearchProgress(
                    stage=stage_name,
                    status="failed" if stage_name in ctx.failed_stages else "completed",
                )
            )
    return ctx
