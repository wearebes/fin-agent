"""Runtime container assembly for the fin-agent."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fin_agent.adapters.llm.codex import LocalCodex
from fin_agent.adapters.llm.disabled import DisabledLLM
from fin_agent.adapters.llm.openai.client import OpenAIClient
from fin_agent.adapters.market_data.router import MarketDataRouter
from fin_agent.adapters.search.exa.client import ExaSearchClient
from fin_agent.adapters.search.tavily.client import TavilySearchClient
from fin_agent.bootstrap.settings import AppSettings, collect_runtime_validation_errors
from fin_agent.domain.constants import SearchProviderName
from fin_agent.services.auth import AuthConfig, AuthService
from fin_agent.services.model_connections import ModelConnections
from fin_agent.services.research import ResearchService
from fin_agent.services.skill_router import SkillDispatcher
from fin_agent.skills import SkillRegistry
from fin_agent.skills.loader import build_default_skill_catalog
from fin_agent.skills.manifest import SkillCatalog
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.run_store import InMemoryRunStore, RunStore
from fin_agent.storage.user_store import InMemoryUserStore, SQLAlchemyUserStore, UserStore
from fin_agent.workflows.research.stages import StageDeps
from fin_agent.workflows.research.stages.tools import build_default_tool_registry

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
    model_connections: ModelConnections
    local_codex: LocalCodex
    # Pure-descriptor projection of skill_catalog, consumed only by
    # GET /v1/skills. Intentionally NOT part of StageDeps — no stage browses
    # it; ResearchService reaches the full catalog only through the dispatcher.
    skill_registry: SkillRegistry
    # Full manifests (incl. provenance) — the management endpoints
    # (GET /v1/skills/details, DELETE /v1/skills/{name}) read `source` from
    # here to distinguish builtin from external. The dispatcher used by the
    # workflow is built off this same catalog inside reload_skills().
    skill_catalog: SkillCatalog
    # Serialises concurrent reload_skills() calls so two in-flight installs
    # cannot interleave their three-field rebind (catalog/dispatcher/registry)
    # and leave the container in a torn, mutually-inconsistent state.
    _reload_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def external_skills_dir(self) -> Path:
        """The on-disk pool the install/upload/delete endpoints mutate."""
        return Path(self.settings.runtime.data_dir) / "skills"

    def reload_skills(self) -> int:
        """Re-scan the skill dirs and atomically swap in the fresh catalog.

        Called after an install/upload/delete mutates ``<data_dir>/skills/``.
        Rebuilds the catalog from disk, derives a new dispatcher + registry,
        and rebinds all three under ``_reload_lock`` so a concurrent reload
        cannot observe a half-updated container. Returns the new skill count.
        """
        new_catalog = build_default_skill_catalog(external_dir=self.external_skills_dir)
        new_dispatcher = SkillDispatcher(new_catalog)
        with self._reload_lock:
            self.skill_catalog = new_catalog
            self.research_service.swap_dispatcher(new_dispatcher)
            self.skill_registry = new_catalog.to_registry()
        return len(self.skill_registry.list())


def _build_stores(settings: AppSettings) -> tuple[RunStore, UserStore]:
    db = settings.database
    if db.backend != "sql":
        logger.info("Using in-memory run and user stores")
        return InMemoryRunStore(), InMemoryUserStore()

    if db.url.startswith("sqlite:///./"):
        Path(db.url.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)
    run_store = SQLAlchemyRunStore(database_url=db.url, echo=db.echo)
    user_store = SQLAlchemyUserStore(database_url=db.url, echo=db.echo)
    # Each store owns its engine, including a separate database for SQLite :memory:.
    run_store.create_tables()
    user_store.create_tables()
    logger.info("Using SQLAlchemy run and user stores")
    return run_store, user_store


def _build_auth_service(user_store: UserStore, settings: AppSettings) -> AuthService:
    auth_cfg = settings.auth
    config = AuthConfig(
        secret_key=auth_cfg.secret_key.get_secret_value(),
        algorithm=auth_cfg.algorithm,
        access_token_expire_minutes=auth_cfg.access_token_expire_minutes,
    )
    return AuthService(user_store=user_store, config=config)


def _build_search_provider(settings: AppSettings) -> ExaSearchClient | TavilySearchClient:
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

    run_store, user_store = _build_stores(settings)
    auth_service = _build_auth_service(user_store, settings)

    llm = (
        OpenAIClient(settings.openai)
        if settings.runtime.allow_system_model and not settings.runtime.commercial_mode
        else DisabledLLM()
    )
    search = _build_search_provider(settings)
    market_data = MarketDataRouter(
        yfinance_config=settings.market_data,
        akshare_config=settings.akshare,
        fmp_config=settings.fmp,
    )

    # Single shared tool catalog, built once at startup (no longer rebuilt on
    # every tool-exec call). Future MCP sources merge into this same registry.
    tool_registry = build_default_tool_registry(search, market_data)

    deps = StageDeps(
        llm=llm,
        search=search,
        market_data=market_data,
        tool_registry=tool_registry,
        config=settings.research_workflow,
    )

    # Full manifests (body + provenance) live in the catalog; the dispatcher
    # is the only thing that resolves names from it. `skill_registry` below is
    # a body-less projection — the one piece of this that the API may expose.
    skill_catalog = build_default_skill_catalog(
        external_dir=Path(settings.runtime.data_dir) / "skills"
    )
    skill_dispatcher = SkillDispatcher(skill_catalog)

    return Container(
        settings=settings,
        run_store=run_store,
        user_store=user_store,
        research_service=ResearchService(
            environment=settings.app.environment,
            providers=settings.providers.default_selection.model_dump(mode='json'),
            run_store=run_store,
            deps=deps,
            skill_dispatcher=skill_dispatcher,
        ),
        auth_service=auth_service,
        skill_registry=skill_catalog.to_registry(),
        skill_catalog=skill_catalog,
        model_connections=ModelConnections(
            settings.runtime.llm_allowed_hosts,
            proxy_url=settings.proxy.https or settings.proxy.http,
        ),
        local_codex=LocalCodex(settings.codex),
    )
