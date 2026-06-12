"""Install, validate, and remove external skill manifests on disk.

The skill catalog discovers skills by scanning
``<data_dir>/skills/<name>/SKILL.md`` (see :mod:`fin_agent.skills.loader`).
This module is the *write* side of that contract: it materialises new
``SKILL.md`` files into that external pool and removes them again, so the
management API can grow the catalog at runtime without a redeploy. Making a
freshly-written skill actually visible is a separate step
(:meth:`fin_agent.bootstrap.container.Container.reload_skills`) — this module
only touches the filesystem.

Everything here is stdlib-only (``urllib`` for the URL fetch) so installing a
skill adds no new runtime dependency. The safety-critical invariants all live
here:

- **Name validation** (``^[a-zA-Z0-9_-]+$``) — the resolved name becomes a
  directory under the external pool, so it must never contain ``/`` or ``..``;
  this is the path-traversal guard.
- **Size + timeout caps** on URL downloads — a hostile or runaway URL cannot
  stream unbounded bytes or hang the request thread.
- **Builtin protection** — shipped skills are never deletable.
- **Atomic writes** — a half-written ``SKILL.md`` is never visible to a
  concurrent scan; we write a temp file and ``os.replace`` it into place.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fin_agent.skills.loader import SKILL_FILENAME
from fin_agent.skills.manifest import parse_skill_md

logger = logging.getLogger(__name__)

MAX_SKILL_BYTES = 512 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 15
MAX_NAME_LENGTH = 64

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


class SkillInstallError(ValueError):
    """Invalid install input: bad name, unparseable content, or download failure."""


@dataclass(frozen=True, slots=True)
class InstalledSkill:
    """Outcome of a successful install — what landed on disk, and where."""

    name: str
    path: str
    overwritten: bool


def _validate_name(name: str) -> str:
    """Return the cleaned name, or raise if it is unsafe for use as a directory."""
    cleaned = name.strip()
    if not cleaned:
        raise SkillInstallError("Skill name is empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise SkillInstallError(
            f"Skill name '{cleaned}' exceeds {MAX_NAME_LENGTH} characters."
        )
    if not _NAME_RE.match(cleaned):
        raise SkillInstallError(
            f"Invalid skill name '{cleaned}': only letters, digits, '-' and '_' are allowed."
        )
    return cleaned


def _resolve_name(fields: dict[str, Any], name_hint: str | None) -> str:
    """Pick the skill's name: frontmatter ``name`` wins, else the caller's hint.

    The chosen name is also the directory we create, so the manifest name and
    its directory always agree (the loader keys a manifest off its frontmatter
    ``name``, falling back to the directory name).
    """
    raw = fields.get("name") or name_hint or ""
    return _validate_name(str(raw))


def install_from_content(
    content: str, name_hint: str | None, external_dir: Path | str
) -> InstalledSkill:
    """Write a SKILL.md document into the external pool under its resolved name.

    ``name_hint`` (e.g. an uploaded filename's stem) is consulted only when the
    document's frontmatter omits a ``name``. The write is atomic: the file
    appears in full or not at all, even under a concurrent catalog scan.
    """
    if not content.strip():
        raise SkillInstallError("Skill content is empty.")

    fields = parse_skill_md(content)
    name = _resolve_name(fields, name_hint)

    skill_dir = Path(external_dir) / name
    target = skill_dir / SKILL_FILENAME
    overwritten = target.exists()

    skill_dir.mkdir(parents=True, exist_ok=True)
    # Temp file in the *same* directory so os.replace is an atomic rename on one
    # filesystem rather than a cross-device copy. The leading dot keeps the
    # loader (which only reads SKILL.md) from ever picking it up mid-write.
    fd, tmp_name = tempfile.mkstemp(dir=skill_dir, prefix=".skill-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

    logger.info(
        "Installed external skill '%s' at %s (overwritten=%s)", name, target, overwritten
    )
    return InstalledSkill(name=name, path=str(target), overwritten=overwritten)


def _derive_name_from_url(url: str) -> str | None:
    """Best-effort name hint from a URL path; used only if frontmatter omits one.

    ``.../valuation/SKILL.md`` -> ``"valuation"``; ``.../my-skill.md`` ->
    ``"my-skill"``. Returns ``None`` when nothing usable can be salvaged, in
    which case the frontmatter must supply the name or the install is rejected.
    """
    segments = [seg for seg in urlparse(url).path.split("/") if seg]
    if not segments:
        return None
    last = segments[-1]
    if last.lower() == SKILL_FILENAME.lower() and len(segments) >= 2:
        candidate = segments[-2]
    else:
        candidate = last
        if candidate.lower().endswith(".md"):
            candidate = candidate[: -len(".md")]
    return candidate or None


def install_from_url(url: str, external_dir: Path | str) -> InstalledSkill:
    """Download a SKILL.md from an http(s) URL and install it into the pool.

    Enforces an http/https scheme, a 15s timeout, and a 512 KB size cap so a
    hostile or runaway URL cannot hang the worker or exhaust memory.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise SkillInstallError(
            f"Unsupported URL scheme '{parsed.scheme or '(none)'}': only http/https allowed."
        )
    if not parsed.netloc:
        raise SkillInstallError("URL is missing a host.")

    request = urllib.request.Request(
        url, headers={"User-Agent": "fin-agent-skill-installer"}
    )
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
            raw = resp.read(MAX_SKILL_BYTES + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise SkillInstallError(f"Failed to download skill from URL: {exc}") from exc

    if len(raw) > MAX_SKILL_BYTES:
        raise SkillInstallError(
            f"Downloaded skill exceeds the {MAX_SKILL_BYTES // 1024} KB limit."
        )
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillInstallError("Downloaded skill is not valid UTF-8 text.") from exc

    return install_from_content(content, _derive_name_from_url(url), external_dir)


def uninstall(name: str, external_dir: Path | str, builtin_dir: Path | str) -> str:
    """Remove an external skill's directory from the pool; return its name.

    Refuses to delete a shipped builtin (``builtin_dir/<name>`` exists) with
    ``PermissionError``, and raises ``FileNotFoundError`` when no external skill
    by that name is installed. The name is validated first, so the delete path
    can never escape the external pool.
    """
    cleaned = _validate_name(name)

    if (Path(builtin_dir) / cleaned).is_dir():
        raise PermissionError(f"Skill '{cleaned}' is a builtin and cannot be removed.")

    external_root = Path(external_dir)
    skill_dir = external_root / cleaned
    # Defence in depth: a validated name is already traversal-free, but confirm
    # the resolved target is a direct child of the external pool before rmtree.
    if skill_dir.resolve().parent != external_root.resolve():
        raise SkillInstallError(f"Refusing to remove out-of-pool path for '{cleaned}'.")
    if not skill_dir.is_dir():
        raise FileNotFoundError(f"No external skill named '{cleaned}' is installed.")

    shutil.rmtree(skill_dir)
    logger.info("Uninstalled external skill '%s' from %s", cleaned, skill_dir)
    return cleaned
