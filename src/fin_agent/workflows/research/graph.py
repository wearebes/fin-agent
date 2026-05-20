"""Stage-plan builder for the scaffold research workflow."""

from fin_agent.workflows.research.config import ResearchWorkflowConfig


def build_stage_plan(config: ResearchWorkflowConfig) -> list[str]:
    stages = ['intake', 'plan', 'retrieve', 'tool-exec', 'synthesize']
    if config.enable_review:
        stages.append('review')
    stages.append('persist')
    return stages
