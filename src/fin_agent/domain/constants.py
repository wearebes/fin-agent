from enum import StrEnum


class EnvironmentName(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PROD = "prod"


class LLMProviderName(StrEnum):
    OPENAI = "openai"


class MarketDataProviderName(StrEnum):
    YFINANCE = "yfinance"


class SearchProviderName(StrEnum):
    EXA = "exa"


class WorkflowName(StrEnum):
    RESEARCH = "research"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    INDEX = "index"
    FOREX = "forex"
    BOND = "bond"
    COMMODITY = "commodity"


class FinancialStatementType(StrEnum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"


class DataFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class AuditOpinionType(StrEnum):
    STANDARD_UNQUALIFIED = "standard_unqualified"
    QUALIFIED = "qualified"
    ADVERSE = "adverse"
    DISCLAIMER_OF_OPINION = "disclaimer_of_opinion"


class NewsUrgencyLevel(StrEnum):
    ROUTINE = "routine"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class RegulatoryRedLineStatus(StrEnum):
    SAFE = "safe"
    WARNING = "warning"
    BREACHED = "breached"
