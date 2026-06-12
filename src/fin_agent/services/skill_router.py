"""Routes a request's selected skill name to its full manifest.

This is the single seam between the API boundary — where a skill is just an
opaque ``selected_skill: str | None`` chosen from ``GET /v1/skills`` — and the
workflow, which only ever sees a resolved instruction string
(``ResearchContext.skill_instructions``). Stages never touch the catalog
directly: they cannot enumerate it, probe it, or resolve names themselves.
"""

from __future__ import annotations

from fin_agent.skills.manifest import SkillCatalog, SkillManifest


class SkillDispatcher:
    """Resolves an opaque skill name to its manifest, or ``None``."""

    def __init__(self, catalog: SkillCatalog) -> None:
        self._catalog = catalog

    def resolve(self, selected_skill: str | None) -> SkillManifest | None:
        """Look up a skill by name.

        Returns ``None`` for "no skill selected" *and* "unknown name" alike —
        callers treat both as "inject nothing", which is the correct behaviour
        for a stale or tampered-with client value.
        """
        if not selected_skill:
            return None
        return self._catalog.get(selected_skill.strip())
