"""Skills catalog skeleton.

A :class:`Skill` here is a *pure descriptor* used for catalog discovery
(``GET /v1/skills``). It deliberately carries no ``handler`` and is not wired
into the stage graph.

Why no dispatch here: ``tool_exec`` is itself one of the stages orchestrated by
``execute_workflow``. If a skill's handler were "run ``execute_workflow`` again"
and execution could delegate to it, the inner ``execute_workflow`` would re-run
``intake → plan → tool-exec → ...`` and the inner ``tool_exec`` would very
likely make the same delegation decision — graph-within-graph recursion. So
"how a matched skill actually dispatches" belongs to the request-routing layer
that runs *before* the stage graph starts, a later phase that is out of scope
here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fin_agent.domain.types import JsonDict


class SkillTrigger(BaseModel):
    slash: str = Field(..., description="Primary slash trigger, e.g. '/research'.")
    aliases: list[str] = Field(
        default_factory=list, description="Alternative trigger words."
    )


class Skill(BaseModel):
    """A catalog descriptor for a skill. No executable handler by design."""

    name: str = Field(..., description="Unique skill name.")
    trigger: SkillTrigger = Field(..., description="How the skill is triggered.")
    description: str = Field(default="", description="Human-readable description.")
    input_schema: JsonDict = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="JSON Schema describing the skill inputs.",
    )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        return [self._skills[name] for name in sorted(self._skills.keys())]

    def resolve_trigger(self, text: str) -> Skill | None:
        """Resolve a leading trigger token to a skill.

        Reserved for the next-phase routing layer; for now only the catalog
        view consumes this registry.
        """
        token = text.strip().split()[0] if text.strip() else ""
        if not token:
            return None
        for skill in self._skills.values():
            if token == skill.trigger.slash or token in skill.trigger.aliases:
                return skill
            # Allow alias matching without a leading slash, e.g. "analyze ...".
            bare = token.lstrip("/")
            if bare == skill.trigger.slash.lstrip("/") or bare in skill.trigger.aliases:
                return skill
        return None


def build_default_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="research",
            trigger=SkillTrigger(slash="/research", aliases=["analyze", "investigate"]),
            description=(
                "Run a full multi-stage financial research workflow: plan, "
                "retrieve, synthesize, review."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "ticker": {"type": "string"},
                },
                "required": ["question"],
            },
        )
    )
    return registry
