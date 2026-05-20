"""Research service that currently returns scaffold planning results only."""

from __future__ import annotations

from uuid import uuid4

from fin_agent.domain.constants import EnvironmentName, RunStatus
from fin_agent.domain.types import EvidenceItem, ResearchRequest, RunResult, TraceRecord
from fin_agent.storage.run_store import RunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.graph import build_stage_plan


class ResearchService:
    def __init__(
        self,
        environment: EnvironmentName,
        providers: dict[str, str],
        workflow_config: ResearchWorkflowConfig,
        run_store: RunStore,
    ) -> None:
        self._environment = environment
        self._providers = providers
        self._workflow_config = workflow_config
        self._run_store = run_store

    def run(self, request: ResearchRequest) -> RunResult:
        stages = build_stage_plan(self._workflow_config)
        evidence = [
            EvidenceItem(
                source='scaffold',
                summary=(
                    'Scaffold only: this run did not call external LLM, search, '
                    'or market-data providers. '
                    f'It only exposed the configured stage plan with up to '
                    f'{self._workflow_config.max_tool_calls} tool calls.'
                ),
            )
        ]
        trace = [
            TraceRecord(
                stage='intake',
                detail=f'Accepted research request for scaffold planning: {request.question}',
            ),
            TraceRecord(
                stage='plan',
                detail=(
                    f'Generated a scaffold stage plan with {len(stages)} stages and '
                    f'provider selections {self._providers}. '
                    'No external retrieval, model inference, or market-data calls were '
                    'executed.'
                ),
            ),
            TraceRecord(
                stage='persist',
                detail=(
                    'Saved the scaffold run to the in-memory run store only. '
                    'No database writes were performed.'
                ),
            ),
        ]
        run = RunResult(
            run_id=uuid4().hex,
            status=RunStatus.COMPLETED,
            environment=self._environment,
            request=request,
            providers=self._providers,
            planned_stages=stages,
            evidence=evidence[: self._workflow_config.evidence_limit],
            trace=trace,
        )
        self._run_store.save(run)
        return run

    def get_run(self, run_id: str) -> RunResult | None:
        return self._run_store.get(run_id)

    def get_trace(self, run_id: str) -> list[TraceRecord] | None:
        return self._run_store.get_trace(run_id)
