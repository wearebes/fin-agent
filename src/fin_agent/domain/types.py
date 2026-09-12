from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from fin_agent.domain.constants import (
    AssetType,
    AuditOpinionType,
    DataFrequency,
    EnvironmentName,
    FinancialStatementType,
    NewsUrgencyLevel,
    RegulatoryRedLineStatus,
    RunStatus,
)
from fin_agent.domain.reports import ReportData


class ResearchTurn(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    answer: str = Field(..., max_length=4000)
    ticker: str | None = Field(default=None, max_length=64)


class ResearchProgress(BaseModel):
    stage: str
    status: Literal["running", "completed", "failed", "skipped"]


class ResearchRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, description="Research question to answer."
    )
    ticker: str | None = Field(
        default=None, description="Optional ticker symbol."
    )
    template: str = Field(
        default="open_research", description="Prompt and output template name."
    )
    lang: str = Field(
        default="zh", description="Output language: 'zh' for native Chinese, 'en' for English."
    )
    selected_skill: str | None = Field(
        default=None,
        description=(
            "Name of a skill explicitly picked via the '/' picker (matches "
            "Skill.name from GET /v1/skills). Not parsed from `question` — "
            "the client sends it as an explicit, opaque catalog key."
        ),
    )
    mode: Literal["auto", "plan"] = Field(
        default="auto",
        description=(
            "'auto' (default) runs the full workflow in one blocking call. "
            "'plan' pauses after the planning stage in status='awaiting_approval' "
            "so the caller can review/edit the retrieval plan before resuming "
            "via POST /v1/research/runs/{run_id}/approve."
        ),
    )
    history: list[ResearchTurn] = Field(default_factory=list, max_length=3)


class EvidenceItem(BaseModel):
    source: str
    summary: str


class TraceRecord(BaseModel):
    stage: str
    detail: str


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


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    environment: EnvironmentName
    request: ResearchRequest
    providers: dict[str, str]
    planned_stages: list[str]
    plan: RetrievalPlan | None = Field(
        default=None,
        description=(
            "Retrieval plan, populated when status=='awaiting_approval' "
            "(mode='plan') and echoed on the final result for transparency."
        ),
    )
    report: str = Field(default="", description="Synthesized research report text.")
    evidence: list[EvidenceItem]
    trace: list[TraceRecord]
    report_data: ReportData | None = None


class TraceResponse(BaseModel):
    run_id: str
    trace: list[TraceRecord]


JsonDict = dict[str, Any]


class MarketDataPoint(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    asset_type: AssetType = Field(..., description="Type of the asset.")
    trade_date: date = Field(..., description="Trading date.")
    open: float = Field(..., description="Opening price.")
    high: float = Field(..., description="Highest price.")
    low: float = Field(..., description="Lowest price.")
    close: float = Field(..., description="Closing price.")
    volume: int | None = Field(default=None, description="Trading volume.")
    turnover: float | None = Field(default=None, description="Trading turnover.")
    pe_ttm: float | None = Field(default=None, description="TTM P/E ratio.")
    pb: float | None = Field(default=None, description="Price-to-book ratio.")
    net_inflow_main: float | None = Field(
        default=None, description="Net inflow of main-force capital."
    )
    open_interest: float | None = Field(
        default=None, description="Futures open interest."
    )


class MarketDataResponse(BaseModel):
    ticker: str
    asset_type: AssetType
    frequency: DataFrequency = Field(default=DataFrequency.DAILY)
    data: list[MarketDataPoint] = Field(default_factory=list)
    source: str | None = None
    currency: str | None = None
    price_basis: str | None = None


class FinancialStatementRecord(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    statement_type: FinancialStatementType = Field(
        ..., description="Which financial statement."
    )
    fiscal_year: int = Field(..., description="Fiscal year.")
    fiscal_quarter: int | None = Field(
        default=None, description="Fiscal quarter (1-4), None=annual."
    )
    revenue_yoy: float | None = Field(
        default=None, description="Revenue YoY growth rate."
    )
    net_profit_margin: float | None = Field(
        default=None, description="Net profit margin."
    )
    net_operating_cash_flow: float | None = Field(
        default=None, description="Net operating cash flow."
    )
    solvency_adequacy_ratio: float | None = Field(
        default=None, description="Solvency adequacy ratio."
    )
    premium_income: float | None = Field(
        default=None, description="Premium income (insurance)."
    )
    inventory_turnover_days: float | None = Field(
        default=None, description="Inventory turnover days."
    )
    total_revenue: float | None = Field(default=None, description="Total revenue.")
    net_income: float | None = Field(default=None, description="Net income.")
    total_assets: float | None = Field(default=None, description="Total assets.")
    total_liabilities: float | None = Field(
        default=None, description="Total liabilities."
    )
    total_equity: float | None = Field(
        default=None, description="Total shareholders equity."
    )
    operating_cash_flow: float | None = Field(
        default=None, description="Cash from operating activities."
    )
    free_cash_flow: float | None = Field(
        default=None, description="Free cash flow."
    )


class FinancialStatementResponse(BaseModel):
    ticker: str
    statement_type: FinancialStatementType
    data: list[FinancialStatementRecord] = Field(default_factory=list)
    source: str | None = None
    currency: str | None = None


class AnalystRecommendation(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    firm: str | None = Field(default=None, description="Analyst firm name.")
    rating: str | None = Field(
        default=None, description="Rating text (Buy/Hold/Sell)."
    )
    target_price: float | None = Field(default=None, description="Target price.")
    rating_date: date | None = Field(default=None, description="Rating date.")


class EarningsEstimate(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    period: str = Field(
        ..., description="Fiscal period estimated (e.g. 2025Q2)."
    )
    eps_estimate: float | None = Field(
        default=None, description="Consensus EPS estimate."
    )
    eps_actual: float | None = Field(
        default=None, description="Actual EPS (None if not reported)."
    )
    revenue_estimate: float | None = Field(
        default=None, description="Consensus revenue estimate."
    )
    revenue_actual: float | None = Field(
        default=None, description="Actual revenue (None if not reported)."
    )


class AnalystResponse(BaseModel):
    ticker: str
    recommendations: list[AnalystRecommendation] = Field(default_factory=list)
    earnings_estimates: list[EarningsEstimate] = Field(default_factory=list)


class CompanyInfo(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    name: str | None = Field(default=None, description="Company name.")
    sector: str | None = Field(default=None, description="Sector classification.")
    industry: str | None = Field(
        default=None, description="Industry classification."
    )
    country: str | None = Field(
        default=None, description="Country of incorporation."
    )
    market_cap: float | None = Field(
        default=None, description="Market capitalization."
    )
    description: str | None = Field(
        default=None, description="Business description."
    )
    employees: int | None = Field(default=None, description="Number of employees.")
    founded_year: int | None = Field(default=None, description="Year founded.")


class CryptoDataPoint(BaseModel):
    ticker: str = Field(..., description="Crypto symbol (e.g. BTC-USD).")
    trade_date: date = Field(..., description="Trading date.")
    open: float = Field(..., description="Opening price.")
    high: float = Field(..., description="Highest price.")
    low: float = Field(..., description="Lowest price.")
    close: float = Field(..., description="Closing price.")
    volume: float | None = Field(default=None, description="Trading volume.")
    market_cap: float | None = Field(
        default=None, description="Market capitalization."
    )
    circulating_supply: float | None = Field(
        default=None, description="Circulating supply."
    )


class CryptoDataResponse(BaseModel):
    ticker: str
    data: list[CryptoDataPoint] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    title: str = Field(..., description="Title of the search result.")
    url: str = Field(..., description="URL of the search result.")
    text: str | None = Field(default=None, description="Snippet / body text.")
    score: float | None = Field(
        default=None, description="Relevance score from provider."
    )


class SearchResponse(BaseModel):
    query: str = Field(..., description="Original search query.")
    results: list[SearchResultItem] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """MCP-compatible tool / function definition.

    ``input_schema`` is a raw JSON Schema dict — the same shape as MCP's
    ``Tool.inputSchema`` and OpenAI's ``function.parameters``. A single
    definition can be fed losslessly to either side, which is what lets the
    tool registry act as the future MCP insertion seam.
    """

    name: str = Field(..., description="Tool name (unique within a registry).")
    description: str = Field(default="", description="Human/LLM-readable description.")
    input_schema: JsonDict = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="Raw JSON Schema for the tool arguments.",
    )
    source: str = Field(
        default="local",
        description="'local' or 'mcp:<server_name>', reserved for future MCP wiring.",
    )


class ToolCall(BaseModel):
    """A single tool invocation requested by the assistant."""

    id: str = Field(..., description="Provider-assigned call id, echoed in the result.")
    name: str = Field(..., description="Name of the tool to invoke.")
    arguments: JsonDict = Field(
        default_factory=dict, description="Parsed tool arguments (decoded JSON object)."
    )


class LLMMessage(BaseModel):
    role: str = Field(
        ..., description="Message role: system/user/assistant/tool."
    )
    content: str = Field(default="", description="Message content.")
    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Populated when the assistant requests tool calls.",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="For role='tool': the ToolCall.id this result answers.",
    )
    name: str | None = Field(
        default=None, description="For role='tool': the tool name."
    )


class LLMResponse(BaseModel):
    message: LLMMessage = Field(
        ..., description="The assistant response message."
    )
    model: str | None = Field(
        default=None, description="Model used for generation."
    )
    usage_prompt_tokens: int | None = Field(
        default=None, description="Prompt token count."
    )
    usage_completion_tokens: int | None = Field(
        default=None, description="Completion token count."
    )
    finish_reason: str | None = Field(
        default=None, description="Provider finish reason (stop/tool_calls/...)."
    )
    error_code: str | None = Field(
        default=None, description="Sanitized provider failure category."
    )

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls or []

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.message.tool_calls)


class MacroDataPoint(BaseModel):
    country: str = Field(default="CN", description="Country code (CN/US).")
    reference_date: date = Field(..., description="Release / reference date.")
    m2_growth_rate: float | None = Field(
        default=None, description="M2 YoY growth rate."
    )
    lpr_1y: float | None = Field(default=None, description="1-year Loan Prime Rate.")
    lpr_5y: float | None = Field(default=None, description="5-year Loan Prime Rate.")
    cpi_yoy: float | None = Field(
        default=None, description="CPI year-over-year."
    )
    ppi_yoy: float | None = Field(
        default=None, description="PPI year-over-year."
    )
    pmi: float | None = Field(
        default=None, description="PMI (50 = breakeven)."
    )
    fed_funds_rate: float | None = Field(
        default=None, description="Federal Funds Rate (US)."
    )


class MacroDataResponse(BaseModel):
    country: str
    frequency: DataFrequency = Field(default=DataFrequency.MONTHLY)
    data: list[MacroDataPoint] = Field(default_factory=list)


class RiskMetrics(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    as_of_date: date | None = Field(
        default=None, description="Reference date for metrics."
    )
    beta: float | None = Field(
        default=None, description="Beta coefficient vs benchmark."
    )
    var_99: float | None = Field(
        default=None, description="Value at Risk at 99% confidence."
    )
    sharpe_ratio: float | None = Field(default=None, description="Sharpe ratio.")
    related_party_transaction_ratio: float | None = Field(
        default=None, description="Related-party transaction ratio."
    )
    audit_opinion: AuditOpinionType | None = Field(
        default=None, description="Audit opinion type."
    )
    credit_rating: str | None = Field(
        default=None, description="Issuer credit rating (e.g. AAA, AA+)."
    )


class SentimentData(BaseModel):
    ticker: str | None = Field(
        default=None, description="Ticker symbol (None=market-wide)."
    )
    as_of_date: date = Field(..., description="Reference date.")
    sentiment_score: float | None = Field(
        default=None, description="Composite sentiment (-1 to 1)."
    )
    news_urgency_level: NewsUrgencyLevel | None = Field(
        default=None, description="News urgency level."
    )
    rumor_volatility_index: float | None = Field(
        default=None, description="Rumor discussion density index."
    )
    retail_participation_ratio: float | None = Field(
        default=None, description="Retail trading participation ratio."
    )
    fear_greed_index: float | None = Field(
        default=None, description="Fear & Greed index (0-100)."
    )
    option_put_call_ratio: float | None = Field(
        default=None, description="Options put/call ratio."
    )


class SentimentDataResponse(BaseModel):
    ticker: str | None = None
    data: list[SentimentData] = Field(default_factory=list)


class CapitalNetworkData(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    as_of_date: date | None = Field(
        default=None, description="Reference date."
    )
    ultimate_controlling_shareholder: str | None = Field(
        default=None, description="Ultimate beneficial owner."
    )
    cross_shareholding_ratio: float | None = Field(
        default=None, description="Cross-shareholding ratio."
    )
    total_external_guarantee_ratio: float | None = Field(
        default=None, description="External guarantee / net assets ratio."
    )
    abnormal_related_party_flow: float | None = Field(
        default=None, description="Abnormal related-party cash flow."
    )
    pledged_share_percentage: float | None = Field(
        default=None, description="Largest shareholder pledge ratio."
    )


class CapitalNetworkResponse(BaseModel):
    ticker: str
    data: list[CapitalNetworkData] = Field(default_factory=list)


class CommoditySupplyChainData(BaseModel):
    country: str = Field(default="CN", description="Country code.")
    reference_date: date = Field(..., description="Reference date.")
    crude_oil_spot_price: float | None = Field(
        default=None, description="Crude oil spot price (USD/bbl)."
    )
    baltic_dry_index: float | None = Field(
        default=None, description="Baltic Dry Index."
    )
    lithium_carbonate_price: float | None = Field(
        default=None, description="Lithium carbonate price."
    )
    chip_lead_time: float | None = Field(
        default=None, description="Semiconductor lead time (weeks)."
    )
    property_sales_area_yoy: float | None = Field(
        default=None, description="Property sales area YoY growth."
    )
    insurance_claim_settlement_ratio: float | None = Field(
        default=None, description="Insurance claim settlement ratio."
    )


class CommoditySupplyChainResponse(BaseModel):
    country: str
    data: list[CommoditySupplyChainData] = Field(default_factory=list)


class GeoPoliticalRiskData(BaseModel):
    country: str = Field(default="CN", description="Country code.")
    reference_date: date = Field(..., description="Reference date.")
    tariff_rate_by_category: dict[str, float] | None = Field(
        default=None, description="Tariff rates by product category."
    )
    geopolitical_risk_index: float | None = Field(
        default=None, description="Geopolitical risk index."
    )
    regulatory_red_line_status: RegulatoryRedLineStatus | None = Field(
        default=None, description="Regulatory red-line status."
    )
    anti_monopoly_fine_history: list[str] | None = Field(
        default=None, description="Anti-monopoly / compliance fine records."
    )


class GeoPoliticalRiskResponse(BaseModel):
    country: str
    data: list[GeoPoliticalRiskData] = Field(default_factory=list)


class QuantitativeIndicators(BaseModel):
    ticker: str = Field(..., description="Ticker symbol.")
    as_of_date: date | None = Field(
        default=None, description="Reference date."
    )
    rsi_14: float | None = Field(
        default=None, description="14-period RSI."
    )
    macd_divergence: float | None = Field(
        default=None, description="MACD divergence value."
    )
    implied_volatility: float | None = Field(
        default=None, description="Implied volatility."
    )
    momentum_factor_3m: float | None = Field(
        default=None, description="3-month momentum factor."
    )
    size_factor: float | None = Field(
        default=None, description="Market-cap size factor."
    )
    value_growth_spread: float | None = Field(
        default=None, description="Value vs growth valuation spread."
    )
