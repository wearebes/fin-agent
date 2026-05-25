"""Runtime container assembly for the fin-agent."""

from __future__ import annotations

from dataclasses import dataclass

from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.adapters.search.exa.client import ExaSearchClient
from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.services.research import ResearchService
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.stages import StageDeps


class RuntimeSettingsError(RuntimeError):
    pass


@dataclass(slots=True)
class Container:
    settings: AppSettings
    run_store: InMemoryRunStore
    research_service: ResearchService


def build_container(settings: AppSettings) -> Container:
    errors = collect_runtime_validation_errors(settings)
    if errors:
        raise RuntimeSettingsError('\n'.join(errors))

    run_store = InMemoryRunStore()

    llm = OpenAIClient(settings.openai)
    search = ExaSearchClient(settings.search)
    market_data = MarketDataRouter(
        yfinance_config=settings.market_data,
        akshare_config=settings.akshare,
    )

    deps = StageDeps(
        llm=llm,
        search=search,
        market_data=market_data,
        config=settings.research_workflow,
    )

    return Container(
        settings=settings,
        run_store=run_store,
        research_service=ResearchService(
            environment=settings.app.environment,
            providers=settings.providers.default_selection.model_dump(mode='json'),
            workflow_config=settings.research_workflow,
            run_store=run_store,
            deps=deps,
        ),
    )
