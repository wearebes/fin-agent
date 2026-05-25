"""Research service that executes the full research workflow."""

from __future__ import annotations

from uuid import uuid4

from fin_agent.domain.constants import EnvironmentName, RunStatus
from fin_agent.domain.types import ResearchRequest, RunResult, TraceRecord
from fin_agent.storage.run_store import RunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext
from fin_agent.workflows.research.graph import build_stage_plan, execute_workflow
from fin_agent.workflows.research.stages import StageDeps


class ResearchService:
    def __init__(
        self,
        environment: EnvironmentName,
        providers: dict[str, str],
        workflow_config: ResearchWorkflowConfig,
        run_store: RunStore,
        deps: StageDeps,
    ) -> None:
        self._environment = environment
        self._providers = providers
        self._workflow_config = workflow_config
        self._run_store = run_store
        self._deps = deps

    async def run(self, request: ResearchRequest) -> RunResult:
        stages = build_stage_plan(self._workflow_config)
        ctx = ResearchContext(request=request)
        ctx = await execute_workflow(
            ctx,
            self._deps,
            extra_stage_kwargs={"run_store": self._run_store},
        )
        run = RunResult(
            run_id=ctx.run_id or uuid4().hex,
            status=RunStatus.COMPLETED,
            environment=self._environment,
            request=request,
            providers=self._providers,
            planned_stages=stages,
            evidence=ctx.evidence[: self._workflow_config.evidence_limit],
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
