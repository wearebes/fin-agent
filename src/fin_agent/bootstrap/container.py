"""Runtime container assembly for the fin-agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.adapters.search.exa.client import ExaSearchClient
from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.services.research import ResearchService
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.run_store import InMemoryRunStore, RunStore
from fin_agent.workflows.research.stages import StageDeps

logger = logging.getLogger(__name__)


class RuntimeSettingsError(RuntimeError):
    pass


@dataclass(slots=True)
class Container:
    settings: AppSettings
    run_store: RunStore
    research_service: ResearchService


def _build_run_store(settings: AppSettings) -> RunStore:
    db = settings.database
    if db.backend == "sql":
        db_url = db.url
        if db_url.startswith("sqlite:///./"):
            relative_part = db_url[len("sqlite:///./"):]
            db_dir = Path(relative_part).parent
            db_dir.mkdir(parents=True, exist_ok=True)
        store = SQLAlchemyRunStore(database_url=db_url, echo=db.echo)
        store.create_tables()
        logger.info("Using SQLAlchemyRunStore (url=%s)", db_url)
        return store
    return InMemoryRunStore()


def build_container(settings: AppSettings) -> Container:
    errors = collect_runtime_validation_errors(settings)
    if errors:
        raise RuntimeSettingsError('\n'.join(errors))

    run_store = _build_run_store(settings)

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
            run_store=run_store,
            deps=deps,
        ),
    )
