"""Filesystem discovery of skill manifests.

Scans ``<root>/<name>/SKILL.md`` directories and assembles a
:class:`~fin_agent.skills.manifest.SkillCatalog`. Two roots are consulted:

- ``BUILTIN_SKILLS_DIR`` — shipped with the agent (``skills/builtin/``).
- an external pool under ``<data_dir>/skills/`` — empty by default; a future
  import flow (or a user dropping a folder in by hand) populates it without
  any code change here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fin_agent.skills import Skill, build_default_skill_registry
from fin_agent.skills.manifest import SkillCatalog, SkillManifest, parse_skill_md

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "builtin"


def load_skill_manifest(skill_dir: Path, *, source: str) -> SkillManifest | None:
    """Load a single ``<skill_dir>/SKILL.md`` into a manifest.

    Returns ``None`` (logging the reason) when the file is absent or cannot
    be parsed into a valid manifest — a malformed skill must never take the
    whole catalog down.
    """
    skill_md = skill_dir / SKILL_FILENAME
    if not skill_md.is_file():
        return None

    try:
        fields = parse_skill_md(skill_md.read_text(encoding="utf-8"))
    except OSError:
        logger.exception("Failed to read skill manifest at %s", skill_md)
        return None

    name = str(fields.get("name") or skill_dir.name).strip()
    if not name:
        logger.warning("Skipping skill manifest with empty name at %s", skill_md)
        return None

    kwargs: dict[str, Any] = {
        "name": name,
        "description": str(fields.get("description", "")),
        "when_to_use": str(fields.get("when_to_use", "")),
        "version": str(fields.get("version", "0.1.0")),
        "body": str(fields.get("body", "")),
        "source": source,
        "path": str(skill_md),
    }
    aliases = fields.get("aliases")
    if isinstance(aliases, list):
        kwargs["aliases"] = [str(alias) for alias in aliases]
    input_schema = fields.get("input_schema")
    if isinstance(input_schema, dict):
        kwargs["input_schema"] = input_schema

    try:
        return SkillManifest(**kwargs)
    except Exception:
        logger.exception("Skipping invalid skill manifest at %s", skill_md)
        return None


def scan_skill_dir(root: Path, *, source: str) -> list[SkillManifest]:
    """Load every ``<root>/<name>/SKILL.md`` manifest, sorted by directory name.

    A missing root is not an error — it simply yields no manifests, which is
    the steady state for the (currently empty) external pool.
    """
    if not root.is_dir():
        return []
    manifests: list[SkillManifest] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        manifest = load_skill_manifest(entry, source=source)
        if manifest is not None:
            manifests.append(manifest)
    return manifests


def _seed_manifest(skill: Skill, *, source: str) -> SkillManifest:
    """Lift a structural catalog descriptor into a body-less manifest.

    ``build_default_skill_registry`` describes skills whose "instructions"
    *are* the workflow itself (e.g. "research" = the standard pipeline with
    no extra guidance), not injectable prompt text. Routing them through the
    same manifest shape lets :class:`SkillDispatcher` resolve *any* catalog
    name uniformly — selecting one of these is then a deliberate no-op
    (``body=""``) rather than an "unknown skill".

    Assumes ``skill.trigger.slash == f"/{skill.name}"``, which is the
    convention every catalog entry follows; keep it that way when extending
    ``build_default_skill_registry``, or this projection silently drops a
    custom slash.
    """
    return SkillManifest(
        name=skill.name,
        description=skill.description,
        aliases=list(skill.trigger.aliases),
        input_schema=skill.input_schema,
        source=source,
    )


def build_default_skill_catalog(*, external_dir: Path | str | None = None) -> SkillCatalog:
    """Assemble the catalog the running app serves.

    Order matters only in that later registrations win on name collision:
    structural defaults seed first, then shipped builtin skills, then the
    external pool — so a dropped-in skill can deliberately override a
    shipped one by reusing its name.
    """
    catalog = SkillCatalog()
    for skill in build_default_skill_registry().list():
        catalog.register(_seed_manifest(skill, source="builtin"))
    for manifest in scan_skill_dir(BUILTIN_SKILLS_DIR, source="builtin"):
        catalog.register(manifest)
    if external_dir is not None:
        for manifest in scan_skill_dir(Path(external_dir), source="external"):
            catalog.register(manifest)
    return catalog
