"""HTTP routes for the fin-agent scaffold API."""

from fastapi import APIRouter, HTTPException, Request, status

from fin_agent.domain.types import ResearchRequest, RunResult, TraceResponse


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get('/healthz', tags=['health'])
    def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    @router.post('/v1/research/runs', response_model=RunResult, tags=['research'])
    def create_research_run(payload: ResearchRequest, request: Request) -> RunResult:
        return request.app.state.container.research_service.run(payload)

    @router.get('/v1/research/runs/{run_id}', response_model=RunResult, tags=['research'])
    def get_research_run(run_id: str, request: Request) -> RunResult:
        run = request.app.state.container.research_service.get_run(run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' was not found.",
            )
        return run

    @router.get('/v1/research/runs/{run_id}/trace', response_model=TraceResponse, tags=['research'])
    def get_research_trace(run_id: str, request: Request) -> TraceResponse:
        trace = request.app.state.container.research_service.get_trace(run_id)
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace for run '{run_id}' was not found.",
            )
        return TraceResponse(run_id=run_id, trace=trace)

    return router
