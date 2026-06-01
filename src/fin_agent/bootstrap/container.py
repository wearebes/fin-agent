"""Runtime container assembly for the fin-agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.adapters.search.exa.client import ExaSearchClient
from fin_agent.adapters.search.tavily.client import TavilySearchClient
from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.services.auth import AuthService, AuthConfig
from fin_agent.services.research import ResearchService
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.run_store import InMemoryRunStore, RunStore
from fin_agent.storage.user_store import InMemoryUserStore, SQLAlchemyUserStore, UserStore
from fin_agent.domain.constants import SearchProviderName
from fin_agent.workflows.research.stages import StageDeps

logger = logging.getLogger(__name__)


class RuntimeSettingsError(RuntimeError):
    pass


@dataclass(slots=True)
class Container:
    settings: AppSettings
    run_store: RunStore
    user_store: UserStore
    research_service: ResearchService
    auth_service: AuthService


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


def _build_user_store(settings: AppSettings) -> UserStore:
    db = settings.database
    if db.backend == "sql":
        db_url = db.url
        if db_url.startswith("sqlite:///./"):
            relative_part = db_url[len("sqlite:///./"):]
            db_dir = Path(relative_part).parent
            db_dir.mkdir(parents=True, exist_ok=True)
        store = SQLAlchemyUserStore(database_url=db_url, echo=db.echo)
        store.create_tables()
        logger.info("Using SQLAlchemyUserStore (url=%s)", db_url)
        return store
    logger.info("Using InMemoryUserStore")
    return InMemoryUserStore()


def _build_auth_service(user_store: UserStore, settings: AppSettings) -> AuthService:
    auth_cfg = settings.auth
    config = AuthConfig(
        secret_key=auth_cfg.secret_key.get_secret_value(),
        algorithm=auth_cfg.algorithm,
        access_token_expire_minutes=auth_cfg.access_token_expire_minutes,
    )
    return AuthService(user_store=user_store, config=config)


def _build_search_provider(settings: AppSettings):
    provider = settings.providers.default_selection.search
    if provider == SearchProviderName.TAVILY:
        if not settings.tavily.enabled:
            logger.info("TavilySearchClient disabled via config, returning no-op client")
            return TavilySearchClient(settings.tavily.model_copy(update={"api_key": None}))
        logger.info("Using TavilySearchClient")
        return TavilySearchClient(settings.tavily)
    if not settings.search.enabled:
        logger.info("ExaSearchClient disabled via config, returning no-op client")
        return ExaSearchClient(settings.search.model_copy(update={"api_key": None}))
    logger.info("Using ExaSearchClient")
    return ExaSearchClient(settings.search)


def build_container(settings: AppSettings) -> Container:
    errors = collect_runtime_validation_errors(settings)
    if errors:
        raise RuntimeSettingsError('\n'.join(errors))

    run_store = _build_run_store(settings)
    user_store = _build_user_store(settings)
    auth_service = _build_auth_service(user_store, settings)

    llm = OpenAIClient(settings.openai)
    search = _build_search_provider(settings)
    market_data = MarketDataRouter(
        yfinance_config=settings.market_data,
        akshare_config=settings.akshare,
        fmp_config=settings.fmp,
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
        user_store=user_store,
        research_service=ResearchService(
            environment=settings.app.environment,
            providers=settings.providers.default_selection.model_dump(mode='json'),
            run_store=run_store,
            deps=deps,
        ),
        auth_service=auth_service,
    )
