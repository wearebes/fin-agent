"""Background lifecycle and account boundaries, without live LLM charges."""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from test_research_workflow import PLAN_JSON, REVIEW_RESPONSE, _make_deps

from fin_agent.domain.constants import AssetType, EnvironmentName, FinancialStatementType
from fin_agent.domain.research_jobs import JobInput, ResearchJob
from fin_agent.domain.types import (
    FinancialStatementRecord,
    FinancialStatementResponse,
    LLMMessage,
    LLMResponse,
    MarketDataPoint,
    MarketDataResponse,
    ResearchProgress,
    ResearchRequest,
    RunResult,
)
from fin_agent.interfaces.api.jobs_router import build_jobs_router
from fin_agent.services.report_data import build_report_data
from fin_agent.services.research import ResearchService
from fin_agent.services.research_jobs import ResearchJobs
from fin_agent.storage.db_store import SQLAlchemyRunStore
from fin_agent.storage.job_store import JobStore
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig
from fin_agent.workflows.research.context import ResearchContext


def prices(ticker="AAPL", start=0, values=None):
    values = values or [100, 120, 90, 100, 110, 105, 115, 130, 125, 140]
    return MarketDataResponse(
        ticker=ticker,
        asset_type=AssetType.STOCK,
        source="Offline fixture",
        currency="USD",
        data=[
            MarketDataPoint(
                ticker=ticker,
                asset_type=AssetType.STOCK,
                trade_date=date(2025, 1, 1) + timedelta(days=start + i),
                open=v,
                high=v,
                low=v,
                close=v,
            )
            for i, v in enumerate(values)
        ],
    )


def report_data():
    finances = FinancialStatementResponse(
        ticker="AAPL",
        statement_type=FinancialStatementType.INCOME_STATEMENT,
        source="Offline financial fixture",
        currency="USD",
        data=[
            FinancialStatementRecord(
                ticker="AAPL",
                statement_type=FinancialStatementType.INCOME_STATEMENT,
                fiscal_year=2022 + i,
                total_revenue=1000 + i * 200,
                net_income=None if i == 1 else -50 + i * 30,
            )
            for i in range(3)
        ],
    )
    ctx = ResearchContext(
        request=ResearchRequest(question="fixture", ticker="AAPL"),
        metadata={
            "report_market": [
                prices().model_dump(mode="json"),
                prices("SPY", start=2).model_dump(mode="json"),
            ],
            "report_financials": [finances.model_dump(mode="json")],
        },
    )
    return build_report_data(ctx)


def result(request, owner=None):
    return RunResult(
        run_id="fixture-run",
        status="completed",
        environment=EnvironmentName.TEST,
        request=request,
        providers={"owner_user_id": owner} if owner else {},
        planned_stages=[],
        report="Offline test report",
        evidence=[],
        trace=[],
        report_data=report_data(),
    )


class FakeService:
    def __init__(self):
        self.calls = 0
        self.owner = None

    def with_owner(self, owner):
        self.owner = owner
        return self

    def with_llm(self, llm, **kwargs):
        self.owner = kwargs.get("owner_user_id")
        return self

    async def run(self, request, *, on_progress):
        self.calls += 1
        on_progress(ResearchProgress(stage="retrieve", status="running"))
        await asyncio.sleep(0.15)
        return result(request, self.owner)


@pytest.fixture
def app_and_store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    store = JobStore(engine)
    service = FakeService()
    container = SimpleNamespace(
        research_service=service,
        auth_service=SimpleNamespace(get_current_user=lambda token: SimpleNamespace(id=token)),
        settings=SimpleNamespace(
            runtime=SimpleNamespace(allow_system_model=True, commercial_mode=False)
        ),
        model_connections=SimpleNamespace(get=lambda owner: None),
    )
    manager = ResearchJobs(container, store)

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        yield
        await manager.close()

    app = FastAPI(lifespan=lifespan)
    app.state.container = container
    app.state.research_jobs = manager
    app.include_router(build_jobs_router())
    yield app, store, service, container
    engine.dispose()


PAYLOAD = {
    "client_id": "request-123",
    "source": "default",
    "request": {"question": "Background fixture", "ticker": "AAPL"},
}
HEADERS = {"Authorization": "Bearer alice"}


def test_request_returns_before_completion_and_background_survives_no_polling(app_and_store):
    app, store, service, _ = app_and_store
    with TestClient(app) as client:
        submitted = client.post("/v1/research/jobs", json=PAYLOAD, headers=HEADERS)
        assert submitted.status_code == 202
        job_id = submitted.json()["id"]
        assert submitted.json()["status"] == "queued"
        # Browser is no longer waiting on a stream; the service alone advances the task.
        deadline = time.monotonic() + 3
        while store.get(job_id, "alice").status != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        saved = store.get(job_id, "alice")
        assert saved.status == "completed"
        assert saved.result.report_data.charts
        assert service.calls == 1
        assert (
            client.post("/v1/research/jobs", json=PAYLOAD, headers=HEADERS).json()["id"] == job_id
        )
        assert service.calls == 1
        assert (
            client.get("/v1/research/jobs/by-client/request-123", headers=HEADERS).status_code
            == 200
        )


def test_history_and_report_are_private(app_and_store):
    app, _, _, _ = app_and_store
    with TestClient(app) as client:
        job_id = client.post("/v1/research/jobs", json=PAYLOAD, headers=HEADERS).json()["id"]
        other = {"Authorization": "Bearer bob"}
        assert client.get(f"/v1/research/jobs/{job_id}", headers=other).status_code == 404
        assert client.get("/v1/research/jobs", headers=other).json()["jobs"] == []
        assert client.get("/v1/research/jobs").status_code == 401
        own = client.get("/v1/research/jobs", headers=HEADERS)
        assert "owner" not in own.json()["jobs"][0]
        assert "result" not in own.json()["jobs"][0]
        assert own.headers["cache-control"] == "no-store"


def test_personal_api_unavailable_does_not_fall_back(app_and_store):
    app, _, service, _ = app_and_store
    with TestClient(app) as client:
        denied = client.post(
            "/v1/research/jobs", json={**PAYLOAD, "source": "personal"}, headers=HEADERS
        )
        assert denied.status_code == 409
        assert service.calls == 0


def test_restart_keeps_results_and_interrupts_only_pending(tmp_path):
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    engine = create_engine(url)
    store = JobStore(engine)
    for status in ["queued", "running", "completed"]:
        store.save(
            ResearchJob(
                id=status,
                owner="alice",
                client_id=status + "-client",
                request=ResearchRequest(question="fixture"),
                source="default",
                status=status,
                result=result(ResearchRequest(question="fixture"))
                if status == "completed"
                else None,
            )
        )
    engine.dispose()
    engine = create_engine(url)
    reopened = JobStore(engine)
    reopened.interrupt_pending()
    assert reopened.get("queued", "alice").status == "interrupted"
    assert reopened.get("running", "alice").status == "interrupted"
    saved = reopened.get("completed", "alice")
    assert saved.status == "completed"
    assert saved.result.report_data.charts[0].series[0].values[0] == 100
    engine.dispose()


@pytest.mark.asyncio
async def test_worker_exception_is_redacted_and_next_job_runs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'failure.db'}")
    service = FakeService()
    service.run = AsyncMock(
        side_effect=[
            RuntimeError("SECRET-MUST-NOT-LEAK"),
            result(ResearchRequest(question="second")),
        ]
    )
    queue = ResearchJobs(SimpleNamespace(research_service=service), JobStore(engine))
    queue.start()
    first = queue.submit(JobInput.model_validate(PAYLOAD), "alice")
    second = queue.submit(
        JobInput.model_validate({**PAYLOAD, "client_id": "second-request"}), "alice"
    )
    await asyncio.wait_for(queue.queue.join(), 3)
    assert queue.store.get(first.id, "alice").status == "failed"
    assert "SECRET" not in queue.store.get(first.id, "alice").model_dump_json()
    assert queue.store.get(second.id, "alice").status == "completed"
    await queue.close()
    engine.dispose()


def test_figures_compute_returns_drawdown_and_align_comparison_without_filling_gaps():
    data = report_data()
    assert data.narrative == "data_only"
    assert data.metrics[0].value == 40
    assert data.metrics[1].value == -25
    comparison = next(c for c in data.charts if len(c.series) == 2 and c.kind == "line")
    assert comparison.labels[0] == "2025-01-03"
    assert all(s.values[0] == 0 for s in comparison.series)
    financials = next(c for c in data.charts if c.kind == "bar")
    assert financials.unit == "USD"
    assert financials.series[1].values == [-50, None, 10]
    assert len(data.charts) == 4


def test_report_ignores_fabricated_prose_and_sparse_prices():
    ctx = ResearchContext(
        request=ResearchRequest(question="fixture"),
        report="Return 9999%",
        metadata={"report_market": [prices(values=[100, 200]).model_dump()]},
    )
    data = build_report_data(ctx)
    assert not data.charts and not data.metrics
    assert data.gaps


def test_report_figures_persist_with_regular_run_store(tmp_path):
    store = SQLAlchemyRunStore(f"sqlite:///{tmp_path / 'runs.db'}")
    store.create_tables()
    run = result(ResearchRequest(question="fixture"))
    store.save(run)
    loaded = store.get(run.run_id)
    assert loaded.report_data == run.report_data
    store.engine.dispose()


@pytest.mark.asyncio
async def test_full_workflow_produces_figures_and_retains_them_on_llm_failure():
    deps = _make_deps(ResearchWorkflowConfig())
    deps.market_data.get_market_data = lambda *args, **kwargs: prices()
    store = InMemoryRunStore()
    for failed in [False, True]:
        responses = [
            LLMResponse(message=LLMMessage(role="assistant", content=PLAN_JSON)),
            LLMResponse(message=LLMMessage(role="assistant", content="No more tools")),
            RuntimeError("offline quota fixture")
            if failed
            else LLMResponse(message=LLMMessage(role="assistant", content="# Fixture report")),
            REVIEW_RESPONSE,
        ]
        llm = SimpleNamespace(chat=AsyncMock(side_effect=responses))
        service = ResearchService(EnvironmentName.TEST, {}, store, replace(deps, llm=llm))
        run = await service.run(
            ResearchRequest(question="fixture", ticker="AAPL", template="illustrated_research")
        )
        assert run.status == ("failed" if failed else "completed")
        assert run.report_data.narrative == ("data_only" if failed else "ai")
        assert run.report_data.charts[0].series[0].values[0] == 100
        assert run.report_data.metrics[0].value == 40


def test_personal_job_uses_only_own_client_and_closes_it(app_and_store):
    app, store, service, container = app_and_store
    calls = []

    @asynccontextmanager
    async def client(config):
        calls.append("opened")
        yield SimpleNamespace()
        calls.append("closed")

    container.model_connections = SimpleNamespace(
        get=lambda owner: SimpleNamespace(
            config=SimpleNamespace(model="own-model", protocol="openai")
        ),
        client=client,
    )
    service.with_owner = lambda owner: pytest.fail("System model must not be used")
    with TestClient(app) as browser:
        submitted = browser.post(
            "/v1/research/jobs", headers=HEADERS, json={**PAYLOAD, "source": "personal"}
        )
        assert submitted.status_code == 202
        deadline = time.monotonic() + 3
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        saved = store.get(submitted.json()["id"], "alice")
        assert saved.status == "completed"
        assert saved.result.providers["owner_user_id"] == "alice"
        assert calls == ["opened", "closed"]
        assert "api_key" not in saved.model_dump_json()
