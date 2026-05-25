from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fin_agent.domain.constants import AssetType, DataFrequency, FinancialStatementType
from fin_agent.domain.types import EvidenceItem, ResearchRequest, TraceRecord


class SearchPlanItem(BaseModel):
    query: str = Field(..., description="Search query string.")
    max_results: int = Field(default=5, ge=1, le=20)


class MarketDataPlanItem(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    asset_type: AssetType = Field(default=AssetType.STOCK)
    frequency: DataFrequency = Field(default=DataFrequency.DAILY)
    period: str = Field(default="1y")


class FinancialsPlanItem(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    statement_type: FinancialStatementType = Field(
        default=FinancialStatementType.INCOME_STATEMENT
    )
    frequency: DataFrequency = Field(default=DataFrequency.YEARLY)


class RetrievalPlan(BaseModel):
    search_queries: list[SearchPlanItem] = Field(default_factory=list)
    market_data: list[MarketDataPlanItem] = Field(default_factory=list)
    financials: list[FinancialsPlanItem] = Field(default_factory=list)
    fetch_company_info_tickers: list[str] = Field(default_factory=list)
    fetch_analyst_data_tickers: list[str] = Field(default_factory=list)
    fetch_crypto_tickers: list[str] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""


class ResearchContext(BaseModel):
    run_id: str = ""
    request: ResearchRequest
    plan: RetrievalPlan = Field(default_factory=RetrievalPlan)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    trace: list[TraceRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    report: str = ""
    review_passed: bool | None = None
    review_feedback: str = ""
    iteration: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
