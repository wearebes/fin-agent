"""Research service that executes the full research workflow."""

from __future__ import annotations

import logging
from uuid import uuid4

from fin_agent.domain.constants import EnvironmentName, RunStatus
from fin_agent.domain.types import ResearchRequest, RunResult, TraceRecord
from fin_agent.storage.run_store import RunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext
from fin_agent.workflows.research.graph import build_stage_plan, execute_workflow
from fin_agent.workflows.research.stages import StageDeps

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(
        self,
        environment: EnvironmentName,
        providers: dict[str, str],
        run_store: RunStore,
        deps: StageDeps,
    ) -> None:
        self._environment = environment
        self._providers = providers
        self._run_store = run_store
        self._deps = deps

    @property
    def workflow_config(self) -> ResearchWorkflowConfig:
        return self._deps.config

    async def run(self, request: ResearchRequest) -> RunResult:
        stages = build_stage_plan(self.workflow_config)
        ctx = ResearchContext(request=request)
        status = RunStatus.COMPLETED

        try:
            ctx = await execute_workflow(
                ctx,
                self._deps,
                extra_stage_kwargs={"run_store": self._run_store},
            )
        except Exception:
            logger.exception("Workflow execution failed for run_id=%s", ctx.run_id)
            status = RunStatus.FAILED

        if status == RunStatus.COMPLETED:
            failed_stages = [
                t for t in ctx.trace if "failed" in t.detail.lower()
            ]
            if failed_stages:
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

    def get_run(self, run_id: str) -> RunResult | None:
        return self._run_store.get(run_id)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        result = self._run_store.get_trace(run_id)
        if result is None:
            return None
        return result
