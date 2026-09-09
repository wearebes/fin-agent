"""Full, file-backed skill definitions.

A :class:`SkillManifest` carries everything the catalog descriptor
(:class:`fin_agent.skills.Skill`) deliberately omits — prompt body, on-disk
path, version, provenance — while staying projectable to that pure descriptor
via :meth:`SkillManifest.to_descriptor`. Keeping the body here, not on
``Skill``, is what lets ``GET /v1/skills`` stay a safe catalog view: nothing
that reaches the API response can carry injectable prompt text.

:class:`SkillCatalog` is the manifest-side sibling of
:class:`fin_agent.skills.SkillRegistry`: it stores the full records that the
dispatcher resolves and injects, and projects them down to descriptors for
the registry that the API actually serves.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml
from pydantic import BaseModel, Field

from fin_agent.domain.types import JsonDict
from fin_agent.skills import Skill, SkillRegistry, SkillTrigger

logger = logging.getLogger(__name__)

_DEFAULT_INPUT_SCHEMA: JsonDict = {"type": "object", "properties": {}}

# A leading `---` frontmatter block, the same convention SKILL.md files in
# Claude Code / obra-style skill packs use: YAML between two `---` lines,
# followed by a markdown body.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)


def parse_skill_md(text: str) -> dict[str, Any]:
    """Split a SKILL.md document into frontmatter fields plus a markdown body.

    Expected shape::

        ---
        name: valuation
        description: One-line catalog description
        when_to_use: Guidance on when to pick this skill
        ---
        # Body markdown injected into the workflow's prompts...

    Returns a flat dict of the parsed frontmatter keys with an added ``body``
    key holding the trailing markdown. Documents without a recognizable
    frontmatter block are treated as pure body text (frontmatter keys absent).
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {"body": text.strip()}

    frontmatter: Any = None
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        logger.warning("Failed to parse SKILL.md frontmatter as YAML", exc_info=True)
    if not isinstance(frontmatter, dict):
        frontmatter = {}

    return {**frontmatter, "body": text[match.end():].strip()}


class SkillManifest(BaseModel):
    """Full, file-backed skill definition: catalog fields + prompt + provenance."""

    name: str = Field(
        ...,
        description="Unique skill name; also its '/<name>' trigger and directory name.",
    )
    description: str = Field(default="", description="One-line catalog description.")
    when_to_use: str = Field(
        default="", description="Guidance on when this skill should be selected."
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative trigger words besides the primary '/<name>'.",
    )
    input_schema: JsonDict = Field(default_factory=lambda: dict(_DEFAULT_INPUT_SCHEMA))
    version: str = Field(default="0.1.0", description="Manifest version string.")
    source: str = Field(
        default="builtin",
        description="Provenance: 'builtin' (shipped) or 'external' (dropped into the data dir).",
    )
    body: str = Field(
        default="", description="Markdown instructions injected into workflow prompts."
    )
    path: str = Field(
        default="", description="Filesystem path the manifest was loaded from, if any."
    )

    def to_descriptor(self) -> Skill:
        """Project to the pure catalog descriptor exposed via ``GET /v1/skills``.

        Only catalog-safe fields cross this boundary — ``body`` and ``path``
        never do.
        """
        return Skill(
            name=self.name,
            trigger=SkillTrigger(slash=f"/{self.name}", aliases=list(self.aliases)),
            description=self.description,
            input_schema=self.input_schema,
        )


class SkillCatalog:
    """In-memory store of full :class:`SkillManifest` records.

    Manifest-side counterpart of :class:`fin_agent.skills.SkillRegistry`:
    where the registry holds pure descriptors for the API, this holds the
    full records (body, path, provenance) that :class:`SkillDispatcher`
    resolves for prompt injection.
    """

    def __init__(self) -> None:
        self._manifests: dict[str, SkillManifest] = {}

    def register(self, manifest: SkillManifest) -> None:
        self._manifests[manifest.name] = manifest

    def get(self, name: str) -> SkillManifest | None:
        return self._manifests.get(name)

    def list(self) -> list[SkillManifest]:
        return [self._manifests[name] for name in sorted(self._manifests.keys())]

    def to_registry(self) -> SkillRegistry:
        """Project every manifest to its descriptor — the sole feed for ``/v1/skills``."""
        registry = SkillRegistry()
        for manifest in self.list():
            registry.register(manifest.to_descriptor())
        return registry
