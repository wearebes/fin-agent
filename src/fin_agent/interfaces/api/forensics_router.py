"""API routes for evidence-first quantitative strategy audits."""

from fastapi import APIRouter, HTTPException, Request

from fin_agent.domain.forensics import ForensicsReport, ForensicsRequest
from fin_agent.services.forensics import NoMarketDataError


def build_forensics_router() -> APIRouter:
    router = APIRouter(prefix="/v1/quant/forensics", tags=["quant-forensics"])

    @router.post("/runs", response_model=ForensicsReport)
    async def create_forensics_run(payload: ForensicsRequest, request: Request) -> ForensicsReport:
        try:
            return await request.app.state.container.forensics_service.diagnose(payload)
        except NoMarketDataError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
            ) from exc

    return router
