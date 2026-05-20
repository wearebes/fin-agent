"""Runtime container assembly for the fin-agent scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.services.research import ResearchService
from fin_agent.storage.run_store import InMemoryRunStore


class RuntimeSettingsError(RuntimeError):
    pass


@dataclass(slots=True)
class Container:
    settings: AppSettings
    run_store: InMemoryRunStore
    research_service: ResearchService


def build_container(settings: AppSettings) -> Container:
    """Validate settings and assemble the in-memory scaffold runtime."""
    errors = collect_runtime_validation_errors(settings)
    if errors:
        raise RuntimeSettingsError('\n'.join(errors))
    run_store = InMemoryRunStore()
    return Container(
        settings=settings,
        run_store=run_store,
        research_service=ResearchService(
            environment=settings.app.environment,
            providers=settings.providers.default_selection.model_dump(mode='json'),
            workflow_config=settings.research_workflow,
            run_store=run_store,
        ),
    )
