"""Validated inputs for the existing six tools; no SDK-specific tool API required."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fin_agent.domain.constants import AssetType, FinancialStatementType


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=2000)
    max_results: int = Field(default=5, ge=1, le=20)


class TickerInput(ToolInput):
    ticker: str = Field(min_length=1, max_length=64)


class MarketDataInput(TickerInput):
    asset_type: AssetType = AssetType.STOCK
    period: str | None = Field(default=None, min_length=1, max_length=32)
    frequency: Literal["daily", "weekly", "monthly"] = "daily"


class FinancialsInput(TickerInput):
    statement_type: FinancialStatementType = FinancialStatementType.INCOME_STATEMENT
    frequency: Literal["yearly", "quarterly"] = "yearly"


class CryptoInput(TickerInput):
    period: str | None = Field(default=None, min_length=1, max_length=32)
