"""Offline contracts for bounded context and progress delivery."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_research_workflow import PLAN_JSON, REVIEW_RESPONSE, _make_deps

from fin_agent.domain.constants import EnvironmentName
from fin_agent.domain.types import LLMMessage, LLMResponse, ResearchProgress, ResearchRequest
from fin_agent.interfaces.api.router import build_router, research_events
from fin_agent.services.research import ResearchService
from fin_agent.storage.run_store import InMemoryRunStore
from fin_agent.workflows.research.config import ResearchWorkflowConfig


def response(text):
    return LLMResponse(message=LLMMessage(role="assistant", content=text))


@pytest.fixture
def service():
    deps = _make_deps(ResearchWorkflowConfig())
    deps.llm.chat = AsyncMock(
        side_effect=[
            response(PLAN_JSON),
            response("```done```"),
            response("# Offline report\nEvidence-backed analysis."),
            REVIEW_RESPONSE,
        ]
    )
    return ResearchService(EnvironmentName.TEST, {}, InMemoryRunStore(), deps)


def client_for(service):
    app = FastAPI()
    app.state.container = SimpleNamespace(research_service=service)
    app.include_router(build_router())
    return TestClient(app)


def parse_events(text):
    return [
        (
            block.splitlines()[0].removeprefix("event: "),
            json.loads(block.splitlines()[1].removeprefix("data: ")),
        )
        for block in text.strip().split("\n\n")
        if block.startswith("event:")
    ]


def test_stream_returns_real_stages_and_persisted_result(service):
    with client_for(service) as client:
        streamed = client.post("/v1/research/stream", json={"question": "Analyze AAPL"})
        assert streamed.status_code == 200
        assert "text/event-stream" in streamed.headers["content-type"]
        events = parse_events(streamed.text)
        assert events[0] == ("progress", {"stage": "intake", "status": "running"})
        assert ("progress", {"stage": "synthesize", "status": "completed"}) in events
        event, result = events[-1]
        assert event == "result"
        assert result["status"] == "completed"
        assert client.get(f"/v1/research/runs/{result['run_id']}").json() == result
        assert service._deps.llm.chat.await_count == 4


@pytest.mark.asyncio
async def test_history_reaches_all_model_stages_without_extra_calls(service):
    history = [{"question": "Analyze AAPL", "answer": "Earlier report", "ticker": "AAPL"}]
    await service.run(ResearchRequest(question="What about its cash flow?", history=history))
    prompts = [call.args[0][-1].content for call in service._deps.llm.chat.call_args_list]
    assert len(prompts) == 4
    for prompt in prompts:
        assert "Earlier report" in prompt
        assert "untrusted context" in prompt
        assert "What about its cash flow?" in prompt
        assert "explicit ticker take priority" in prompt


@pytest.mark.parametrize(
    "history",
    [
        [{"question": "q", "answer": "a"}] * 4,
        [{"question": "q", "answer": "a" * 4001}],
        [{"question": "q" * 1001, "answer": "a"}],
    ],
)
def test_unbounded_context_rejected_before_any_model_call(service, history):
    with pytest.raises(ValidationError):
        ResearchRequest(question="q", history=history)
    with client_for(service) as client:
        assert (
            client.post(
                "/v1/research/stream",
                json={
                    "question": "q",
                    "history": history,
                },
            ).status_code
            == 422
        )
    service._deps.llm.chat.assert_not_called()


def test_failed_review_is_a_failed_event_and_preserves_report(service):
    service._deps.llm.chat.side_effect = [
        response(PLAN_JSON),
        response("```done```"),
        response("Report kept for inspection"),
        response('{"passed":false,"feedback":"Unsupported claim"}'),
    ]
    with client_for(service) as client:
        events = parse_events(client.post("/v1/research/stream", json={"question": "q"}).text)
    assert ("progress", {"stage": "review", "status": "failed"}) in events
    assert events[-1][1]["status"] == "failed"
    assert events[-1][1]["report"] == "Report kept for inspection"


def test_stream_error_does_not_leak_internal_details_or_retry():
    service = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("private configuration")))
    with client_for(service) as client:
        text = client.post("/v1/research/stream", json={"question": "q"}).text
    assert parse_events(text) == [("error", {"message": "Research could not be completed."})]
    assert "private configuration" not in text
    service.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_progress_arrives_before_completion_and_disconnect_cancels_task():
    cancelled = asyncio.Event()

    async def run(payload, *, on_progress):
        on_progress(ResearchProgress(stage="plan", status="running"))
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    events = research_events(ResearchRequest(question="q"), SimpleNamespace(run=run))
    first = await asyncio.wait_for(anext(events), timeout=1)
    assert '"stage":"plan"' in first
    assert '"status":"running"' in first
    await events.aclose()
    assert cancelled.is_set()
