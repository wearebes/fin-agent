"""Research workflow."""

from fin_agent.workflows.research.context import (
    FinancialsPlanItem,
    MarketDataPlanItem,
    ResearchContext,
    RetrievalPlan,
    SearchPlanItem,
    ToolCallRecord,
)
from fin_agent.workflows.research.graph import (
    build_stage_plan,
    execute_workflow,
    register_stage,
)
from fin_agent.workflows.research.stages import StageDeps, StageFn, ToolRegistry

__all__ = [
    "FinancialsPlanItem",
    "MarketDataPlanItem",
    "ResearchContext",
    "RetrievalPlan",
    "SearchPlanItem",
    "StageDeps",
    "StageFn",
    "ToolCallRecord",
    "ToolRegistry",
    "build_stage_plan",
    "execute_workflow",
    "register_stage",
]
