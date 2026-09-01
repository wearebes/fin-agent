"""Research service that executes the full research workflow."""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import uuid4

from fin_agent.domain.constants import EnvironmentName, RunStatus
from fin_agent.domain.types import ResearchRequest, RetrievalPlan, RunResult, TraceRecord
from fin_agent.services.skill_router import SkillDispatcher
from fin_agent.storage.run_store import RunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext
from fin_agent.workflows.research.graph import (
    ProgressCallback,
    build_resume_stages,
    build_stage_plan,
    execute_workflow,
)
from fin_agent.workflows.research.stages import LLMProvider, StageDeps

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(
        self,
        environment: EnvironmentName,
        providers: dict[str, str],
        run_store: RunStore,
        deps: StageDeps,
        skill_dispatcher: SkillDispatcher,
    ) -> None:
        self._environment = environment
        self._providers = providers
        self._run_store = run_store
        self._deps = deps
        self._skill_dispatcher = skill_dispatcher

    def swap_dispatcher(self, dispatcher: SkillDispatcher) -> None:
        """Hot-swap the skill dispatcher after a catalog reload.

        Called by ``Container.reload_skills`` once a freshly-scanned catalog
        has been built. A single reference rebind: in-flight ``run``/``run_plan``
        calls already captured the previous manifest body and finish against it,
        while every subsequent ``resolve`` sees the new catalog.
        """
        self._skill_dispatcher = dispatcher

    @property
    def workflow_config(self) -> ResearchWorkflowConfig:
        return self._deps.config

    def with_llm(
        self,
        llm: LLMProvider,
        *,
        model: str,
        protocol: str,
        owner_user_id: str | None = None,
        source: str = "personal",
    ) -> ResearchService:
        providers = {
            **self._providers,
            "llm": source,
            "llm_model": model,
            "llm_protocol": protocol,
        }
        if owner_user_id:
            providers["owner_user_id"] = owner_user_id
        return ResearchService(
            self._environment,
            providers,
            self._run_store,
            replace(self._deps, llm=llm),
            self._skill_dispatcher,
        )

    async def run(
        self,
        request: ResearchRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RunResult:
        stages = build_stage_plan(self.workflow_config)
        skill = self._skill_dispatcher.resolve(request.selected_skill)
        ctx = ResearchContext(
            request=request,
            skill_instructions=skill.body if skill else "",
        )
        status = RunStatus.COMPLETED

        try:
            ctx = await execute_workflow(
                ctx,
                self._deps,
                extra_stage_kwargs={"run_store": self._run_store},
                on_progress=on_progress,
            )
        except Exception:
            logger.exception("Workflow execution failed for run_id=%s", ctx.run_id)
            status = RunStatus.FAILED

        if ctx.failed_stages or not ctx.report.strip():
            status = RunStatus.FAILED

        run = RunResult(
            run_id=ctx.run_id or uuid4().hex,
            status=status,
            environment=self._environment,
            request=request,
            providers=self._providers,
            planned_stages=stages,
            report=ctx.report,
            evidence=ctx.evidence[: self.workflow_config.evidence_limit],
            trace=ctx.trace,
        )
        self._run_store.save(run)
        return run

    async def run_plan(
        self,
        request: ResearchRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RunResult:
        """mode='plan' entry point: runs intake+plan only, persists the
        context for later resumption, and returns an awaiting-approval result."""
        stages = build_stage_plan(self.workflow_config)
        skill = self._skill_dispatcher.resolve(request.selected_skill)
        ctx = ResearchContext(
            request=request,
            skill_instructions=skill.body if skill else "",
        )
        try:
            ctx = await execute_workflow(
                ctx,
                self._deps,
                stages=["intake", "plan"],
                on_progress=on_progress,
            )
        except Exception:
            logger.exception("Plan-stage execution failed for run_id=%s", ctx.run_id)
            run = RunResult(
                run_id=ctx.run_id or uuid4().hex,
                status=RunStatus.FAILED,
                environment=self._environment,
                request=request,
                providers=self._providers,
                planned_stages=stages,
                plan=None,
                report="",
                evidence=[],
                trace=ctx.trace,
            )
            self._run_store.save(run)
            return run

        run = RunResult(
            run_id=ctx.run_id or uuid4().hex,
            status=RunStatus.AWAITING_APPROVAL,
            environment=self._environment,
            request=request,
            providers=self._providers,
            planned_stages=stages,
            plan=ctx.plan,
            report="",
            evidence=ctx.evidence,
            trace=ctx.trace,
        )
        self._run_store.save(run)
        self._run_store.save_context(run.run_id, ctx.model_dump_json())
        return run

    async def approve(
        self, run_id: str, edited_plan: RetrievalPlan | None
    ) -> RunResult | None:
        """Resumes a plan-mode run: loads the persisted context, optionally
        replaces `ctx.plan` with the user-edited version, and runs the
        remaining stages to completion. Returns None if no pending plan
        is found for `run_id` (never existed, ran in mode='auto', or was
        already approved)."""
        ctx_json = self._run_store.get_context(run_id)
        if ctx_json is None:
            return None
        self._run_store.delete_context(run_id)
        ctx = ResearchContext.model_validate_json(ctx_json)
        if edited_plan is not None:
            ctx = ctx.model_copy(update={"plan": edited_plan})

        stages = build_stage_plan(self.workflow_config)
        status = RunStatus.COMPLETED

        try:
            ctx = await execute_workflow(
                ctx,
                self._deps,
                stages=build_resume_stages(self.workflow_config),
                extra_stage_kwargs={"run_store": self._run_store},
            )
        except Exception:
            logger.exception("Resume execution failed for run_id=%s", run_id)
            status = RunStatus.FAILED

        if status == RunStatus.COMPLETED:
            failed_stages = [
                t for t in ctx.trace if "failed" in t.detail.lower()
            ]
            if failed_stages:
                status = RunStatus.FAILED

        run = RunResult(
            run_id=ctx.run_id,
            status=status,
            environment=self._environment,
            request=ctx.request,
            providers=self._providers,
            planned_stages=stages,
            plan=ctx.plan,
            report=ctx.report,
            evidence=ctx.evidence[: self.workflow_config.evidence_limit],
            trace=ctx.trace,
        )
        self._run_store.save(run)
        return run

    def get_run(self, run_id: str) -> RunResult | None:
        return self._run_store.get(run_id)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        return self._run_store.get_trace(run_id)
