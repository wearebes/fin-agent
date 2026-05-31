# fin-agent — Agent Development Guide

## Core Development Principle

**Smoke first, then scale.** Before implementing any large feature — new provider, new workflow stage, new API integration — write a minimal runnable demo or smoke script first. Confirm the output looks right, then proceed with full implementation. Never start broad.

---

## Project Overview

`fin-agent` is a financial research agent scaffold written in Python 3.12. It orchestrates LLM reasoning, web search, and market data retrieval through a staged workflow to answer financial research questions.

**Current status**: Real provider calls are wired (OpenAI, AkShare, YFinance, Exa); the research workflow executes stages sequentially. Storage is in-memory only.

---

## Repository Layout

```
src/fin_agent/
  adapters/
    llm/openai/          # OpenAI async client + config
    market_data/
      akshare/           # A-share market data (CN stocks)
      yfinance/          # Global market data
      router.py          # Selects provider by asset type / ticker prefix
    search/exa/          # Exa semantic search client + config
  bootstrap/
    settings.py          # AppSettings (pydantic-settings, layered YAML + env)
    container.py         # Dependency injection — builds all singletons
    app.py               # FastAPI app factory
    cli.py               # Typer CLI entry point
  domain/
    types.py             # All Pydantic domain models (single source of truth)
    constants.py         # Enums: AssetType, RunStatus, provider names, …
  interfaces/api/
    router.py            # FastAPI routes
  services/
    research.py          # ResearchService — orchestrates the workflow
  storage/
    run_store.py         # InMemoryRunStore (will become DB-backed)
  workflows/research/
    graph.py             # Stage registry + execute_workflow()
    context.py           # ResearchContext (mutable state passed through stages)
    config.py            # ResearchWorkflowConfig
    stages/
      core.py            # intake, plan, retrieve
      pipeline.py        # tool_exec, synthesize, review, persist
      tools.py           # Tool wrappers callable from tool-exec stage
configs/
  base.yaml              # Default config values
  environments/          # local.yaml, test.yaml, prod.yaml (override base)
tests/
  conftest.py
```

---

## Architecture Rules

### Layer boundaries (strict)
```
interfaces/api  →  services  →  workflows  →  adapters
                               ↓
                            domain (types, constants)
```
- `domain/` has **no imports** from other internal packages.
- `adapters/` depend only on `domain/`.
- `workflows/` depend on `adapters/` and `domain/`.
- `services/` depend on `workflows/` and `storage/`.
- `interfaces/` depend only on `services/` and `domain/`.
- `bootstrap/` is the composition root — it may import everything.

### Dependency injection
All runtime singletons live in `Container` (`bootstrap/container.py`). Pass dependencies explicitly via `StageDeps` or constructor injection; never import singletons directly in business logic.

### Async
The entire stack is async. All I/O methods must be `async def`. Use `asyncio.gather` for concurrent calls within a stage.

---

## Code Conventions

- **Python 3.12**, type hints everywhere, `from __future__ import annotations` on every file.
- **Pydantic v2** for all data models — define in `domain/types.py` unless tightly scoped to one adapter.
- **pydantic-settings** (`AppSettings`) for configuration — never read `os.environ` directly outside `settings.py`.
- No comments unless the WHY is non-obvious. No docstrings on trivial methods.
- Prefer `dataclass(slots=True)` for internal structs, Pydantic `BaseModel` for domain/API contracts.
- `logger = logging.getLogger(__name__)` per module; no `print()` in library code.
- Config env prefix: `FIN_AGENT__` with `__` as nested delimiter (e.g. `FIN_AGENT__OPENAI__API_KEY`).

---

## Adding a New Adapter

1. Create `src/fin_agent/adapters/<category>/<name>/` with `__init__.py`, `config.py`, `client.py`.
2. `config.py` — a `BaseModel` with `Field` descriptions. Add it to `AppSettings` in `bootstrap/settings.py`.
3. `client.py` — implement the relevant Protocol from `domain/` (e.g. `MarketDataProvider`, `SearchProvider`, `LLMProvider`).
4. Wire the new client in `bootstrap/container.py`.
5. Add a unit test in `tests/adapters/`.

---

## Adding a New Workflow Stage

1. Write an async function `async def my_stage(ctx: ResearchContext, deps: StageDeps) -> ResearchContext` in the appropriate `stages/` file.
2. Register it in `_STAGE_REGISTRY` in `workflows/research/graph.py`.
3. Add it to `build_stage_plan()` if it belongs in the default pipeline.

---

## Configuration System

Priority (highest → lowest):

1. `AppSettings(**init_kwargs)` — programmatic overrides
2. Environment variables (`FIN_AGENT__*`)
3. `.env` file
4. `configs/environments/<env>.yaml`
5. `configs/base.yaml`
6. Pydantic field defaults

Always add new config fields to the appropriate `*Config` model in `settings.py` with a `Field(description=...)`. Run `fin-agent doctor --write-env-example .env.example` to regenerate the example env file.

---

## Testing

```bash
pytest                          # all tests
pytest tests/unit               # unit only
pytest -x -k "test_name"        # single test
```

- **No mocking of real provider clients** unless testing in isolation from network. Integration tests that call real APIs are gated by `pytest.mark.integration`.
- Use `conftest.py` fixtures for `AppSettings` and `Container` instances.
- Assert on domain model fields, not raw dicts.

---

## Common CLI Commands

```bash
fin-agent doctor                             # validate config + secrets
fin-agent research run --question "..." --ticker AAPL
fin-agent api --reload                       # start FastAPI dev server
fin-agent doctor --write-env-example .env.example
```

---

## Environment Setup

```bash
conda env create -f environment.yml
conda activate fin-agent
pip install -e ".[dev]"
cp .env.example .env           # fill in API keys
```

Required secrets in `.env`:
- `FIN_AGENT__OPENAI__API_KEY`
- `FIN_AGENT__SEARCH__API_KEY` (Exa)

---

## Market Data Routing

`MarketDataRouter` (`adapters/market_data/router.py`) dispatches to AkShare or YFinance based on ticker prefix / asset type:
- A-share tickers (e.g. `600519.SH`, `000001.SZ`) → AkShare
- Everything else → YFinance

When adding a new data source, implement the routing logic inside the router rather than in stages or services.

---

## Key Domain Models (domain/types.py)

| Model | Purpose |
|---|---|
| `ResearchRequest` | Input to the research workflow |
| `RunResult` | Final output stored in RunStore |
| `ResearchContext` | Mutable in-flight state across stages |
| `MarketDataPoint` | Normalized OHLCV + fundamentals |
| `SearchResponse` / `SearchResultItem` | Exa search results |
| `LLMMessage` / `LLMResponse` | LLM I/O |
| `TraceRecord` | Per-stage audit trail entry |

Do not add new fields to domain models without considering downstream serialization impact (API schema, RunStore, trace logs).
