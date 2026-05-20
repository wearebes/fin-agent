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
    COMPLETED = "completed"
