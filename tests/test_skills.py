from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fin_agent.bootstrap.app import create_default_app
from fin_agent.services import skill_installer
from fin_agent.services.skill_router import SkillDispatcher
from fin_agent.skills import (
    Skill,
    SkillRegistry,
    SkillTrigger,
    build_default_skill_registry,
)
from fin_agent.skills.loader import (
    BUILTIN_SKILLS_DIR,
    SKILL_FILENAME,
    build_default_skill_catalog,
    load_skill_manifest,
    scan_skill_dir,
)
from fin_agent.skills.manifest import SkillCatalog, SkillManifest, parse_skill_md


class _FakeUrlResponse:
    """Minimal stand-in for urlopen's context manager, for offline URL tests."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int = -1) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class TestSkillRegistry:
    def test_default_registry_lists_research(self):
        registry = build_default_skill_registry()
        names = [s.name for s in registry.list()]
        assert "research" in names

    def test_get_returns_skill(self):
        registry = build_default_skill_registry()
        skill = registry.get("research")
        assert skill is not None
        assert skill.trigger.slash == "/research"
        assert "analyze" in skill.trigger.aliases
        assert skill.input_schema["required"] == ["question"]

    def test_get_unknown_returns_none(self):
        registry = build_default_skill_registry()
        assert registry.get("nonexistent") is None

    def test_register_and_list_sorted(self):
        registry = SkillRegistry()
        registry.register(
            Skill(name="zeta", trigger=SkillTrigger(slash="/zeta"))
        )
        registry.register(
            Skill(name="alpha", trigger=SkillTrigger(slash="/alpha"))
        )
        names = [s.name for s in registry.list()]
        assert names == ["alpha", "zeta"]

    def test_resolve_trigger_by_slash(self):
        registry = build_default_skill_registry()
        skill = registry.resolve_trigger("/research Analyze AAPL momentum")
        assert skill is not None
        assert skill.name == "research"

    def test_resolve_trigger_by_alias(self):
        registry = build_default_skill_registry()
        skill = registry.resolve_trigger("analyze AAPL")
        assert skill is not None
        assert skill.name == "research"

    def test_resolve_trigger_no_match(self):
        registry = build_default_skill_registry()
        assert registry.resolve_trigger("hello there") is None

    def test_skill_model_has_no_handler_field(self):
        # The catalog descriptor must not expose any executable reference.
        fields = set(Skill.model_fields.keys())
        assert "handler" not in fields
        assert fields == {"name", "trigger", "description", "input_schema"}


def test_skills_endpoint_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("FIN_AGENT__OPENAI__API_KEY", "sk-test")
    monkeypatch.setenv("FIN_AGENT__SEARCH__API_KEY", "search-test")

    with (
        patch("fin_agent.adapters.llm.openai.client.AsyncOpenAI"),
        patch("fin_agent.adapters.search.exa.client.Exa"),
    ):
        with TestClient(create_default_app()) as client:
            resp = client.get("/v1/skills")
            assert resp.status_code == 200
            payload = resp.json()
            assert "skills" in payload
            names = [s["name"] for s in payload["skills"]]
            assert "research" in names

            research = next(s for s in payload["skills"] if s["name"] == "research")
            assert research["trigger"] == "/research"
            assert "analyze" in research["aliases"]
            assert research["description"]
            assert research["input_schema"]["required"] == ["question"]

            # No executable handler must leak into the API response.
            assert "handler" not in research


class TestParseSkillMd:
    def test_parses_frontmatter_and_body(self):
        text = (
            "---\n"
            "name: valuation\n"
            "description: A valuation skill\n"
            "aliases: [val, dd]\n"
            "---\n"
            "# Body heading\n"
            "Body content here.\n"
        )
        result = parse_skill_md(text)
        assert result["name"] == "valuation"
        assert result["description"] == "A valuation skill"
        assert result["aliases"] == ["val", "dd"]
        assert result["body"] == "# Body heading\nBody content here."

    def test_no_frontmatter_treated_as_pure_body(self):
        text = "Just plain markdown.\nNo frontmatter block at all."
        assert parse_skill_md(text) == {"body": text}

    def test_malformed_yaml_falls_back_to_body_only(self):
        text = "---\nkey: [unclosed\n---\nBody survives.\n"
        result = parse_skill_md(text)
        assert "key" not in result
        assert result["body"] == "Body survives."

    def test_non_mapping_frontmatter_is_ignored(self):
        text = "---\n- a\n- b\n---\nBody survives.\n"
        result = parse_skill_md(text)
        assert set(result) == {"body"}
        assert result["body"] == "Body survives."


class TestSkillManifest:
    def test_defaults(self):
        manifest = SkillManifest(name="demo")
        assert manifest.description == ""
        assert manifest.when_to_use == ""
        assert manifest.aliases == []
        assert manifest.input_schema == {"type": "object", "properties": {}}
        assert manifest.version == "0.1.0"
        assert manifest.source == "builtin"
        assert manifest.body == ""
        assert manifest.path == ""

    def test_to_descriptor_projects_catalog_safe_fields_only(self):
        manifest = SkillManifest(
            name="valuation",
            description="desc",
            when_to_use="when to use this",
            aliases=["val", "dd"],
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            version="1.2.3",
            source="external",
            body="SECRET INSTRUCTIONS THAT MUST NOT LEAK",
            path="/some/disk/path/SKILL.md",
        )
        descriptor = manifest.to_descriptor()
        assert isinstance(descriptor, Skill)
        assert descriptor.name == "valuation"
        assert descriptor.trigger.slash == "/valuation"
        assert descriptor.trigger.aliases == ["val", "dd"]
        assert descriptor.description == "desc"
        assert descriptor.input_schema == {
            "type": "object", "properties": {"x": {"type": "string"}}
        }
        # body/path/version/source/when_to_use are catalog-unsafe; the
        # projected payload must never carry the manifest's prompt text or
        # filesystem layout.
        dumped = descriptor.model_dump_json()
        assert "SECRET" not in dumped
        assert "disk/path" not in dumped


class TestSkillCatalog:
    def test_register_get_list_sorted(self):
        catalog = SkillCatalog()
        catalog.register(SkillManifest(name="zeta"))
        catalog.register(SkillManifest(name="alpha"))
        assert [m.name for m in catalog.list()] == ["alpha", "zeta"]
        assert catalog.get("alpha") is not None
        assert catalog.get("missing") is None

    def test_register_overwrites_by_name(self):
        catalog = SkillCatalog()
        catalog.register(SkillManifest(name="demo", version="0.1.0"))
        catalog.register(SkillManifest(name="demo", version="0.2.0"))
        assert len(catalog.list()) == 1
        manifest = catalog.get("demo")
        assert manifest is not None
        assert manifest.version == "0.2.0"

    def test_to_registry_projects_every_manifest_in_sorted_order(self):
        catalog = SkillCatalog()
        catalog.register(SkillManifest(name="zeta", description="Z", body="zeta-secret"))
        catalog.register(SkillManifest(name="alpha", description="A", body="alpha-secret"))
        registry = catalog.to_registry()
        assert isinstance(registry, SkillRegistry)
        descriptors = registry.list()
        assert [s.name for s in descriptors] == ["alpha", "zeta"]
        assert all(isinstance(s, Skill) for s in descriptors)
        # Catalog body text must never reach the projected registry's payload.
        dumped = "".join(s.model_dump_json() for s in descriptors)
        assert "alpha-secret" not in dumped
        assert "zeta-secret" not in dumped


class TestSkillLoader:
    def test_load_skill_manifest_reads_frontmatter_and_body(self, tmp_path):
        skill_dir = tmp_path / "demo"
        skill_dir.mkdir()
        (skill_dir / SKILL_FILENAME).write_text(
            "---\n"
            "name: demo\n"
            "description: Demo skill\n"
            "aliases: [d]\n"
            'version: "2.0.0"\n'
            "---\n"
            "Body instructions.\n",
            encoding="utf-8",
        )
        manifest = load_skill_manifest(skill_dir, source="external")
        assert manifest is not None
        assert manifest.name == "demo"
        assert manifest.description == "Demo skill"
        assert manifest.aliases == ["d"]
        assert manifest.version == "2.0.0"
        assert manifest.body == "Body instructions."
        assert manifest.source == "external"
        assert manifest.path == str(skill_dir / SKILL_FILENAME)

    def test_load_skill_manifest_falls_back_to_directory_name(self, tmp_path):
        skill_dir = tmp_path / "fallback-name"
        skill_dir.mkdir()
        (skill_dir / SKILL_FILENAME).write_text(
            "No frontmatter, just body.", encoding="utf-8"
        )
        manifest = load_skill_manifest(skill_dir, source="builtin")
        assert manifest is not None
        assert manifest.name == "fallback-name"
        assert manifest.body == "No frontmatter, just body."

    def test_load_skill_manifest_missing_file_returns_none(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert load_skill_manifest(empty_dir, source="builtin") is None

    def test_load_skill_manifest_skips_blank_name(self, tmp_path):
        skill_dir = tmp_path / "blank"
        skill_dir.mkdir()
        (skill_dir / SKILL_FILENAME).write_text(
            '---\nname: "   "\n---\nBody.', encoding="utf-8"
        )
        assert load_skill_manifest(skill_dir, source="builtin") is None

    def test_scan_skill_dir_returns_sorted_manifests(self, tmp_path):
        for name in ("zeta", "alpha", "mid"):
            d = tmp_path / name
            d.mkdir()
            (d / SKILL_FILENAME).write_text(
                f"---\nname: {name}\n---\nBody {name}.", encoding="utf-8"
            )
        # A stray file alongside the skill directories must not crash the scan.
        (tmp_path / "not-a-dir.txt").write_text("ignore me", encoding="utf-8")

        manifests = scan_skill_dir(tmp_path, source="external")
        assert [m.name for m in manifests] == ["alpha", "mid", "zeta"]
        assert all(m.source == "external" for m in manifests)

    def test_scan_skill_dir_missing_root_returns_empty_list(self, tmp_path):
        assert scan_skill_dir(tmp_path / "does-not-exist", source="external") == []

    def test_scan_skill_dir_skips_subdirs_without_skill_md(self, tmp_path):
        (tmp_path / "no-skill-here").mkdir()
        good = tmp_path / "good"
        good.mkdir()
        (good / SKILL_FILENAME).write_text("---\nname: good\n---\nBody.", encoding="utf-8")

        manifests = scan_skill_dir(tmp_path, source="builtin")
        assert [m.name for m in manifests] == ["good"]


class TestBuildDefaultSkillCatalog:
    def test_seeds_structural_skills_as_body_less_manifests(self):
        catalog = build_default_skill_catalog()
        research = catalog.get("research")
        assert research is not None
        assert research.body == ""
        assert research.source == "builtin"
        # Projects back to the exact descriptor shape the old registry produced.
        descriptor = research.to_descriptor()
        assert descriptor.trigger.slash == "/research"
        assert descriptor.trigger.aliases == ["analyze", "investigate"]

    def test_includes_shipped_builtin_valuation_skill_with_body(self):
        catalog = build_default_skill_catalog()
        valuation = catalog.get("valuation")
        assert valuation is not None
        assert valuation.source == "builtin"
        assert "估值结论" in valuation.body
        assert valuation.to_descriptor().trigger.aliases == ["val", "dd", "diligence"]

    def test_external_dir_entries_load_and_can_override_by_name(self, tmp_path):
        override_dir = tmp_path / "valuation"
        override_dir.mkdir()
        (override_dir / SKILL_FILENAME).write_text(
            "---\nname: valuation\ndescription: Overridden\n---\nOverridden body.",
            encoding="utf-8",
        )
        extra_dir = tmp_path / "extra"
        extra_dir.mkdir()
        (extra_dir / SKILL_FILENAME).write_text(
            "---\nname: extra\ndescription: Extra skill\n---\nExtra body.",
            encoding="utf-8",
        )

        catalog = build_default_skill_catalog(external_dir=tmp_path)

        overridden = catalog.get("valuation")
        assert overridden is not None
        assert overridden.source == "external"
        assert overridden.body == "Overridden body."

        extra = catalog.get("extra")
        assert extra is not None
        assert extra.source == "external"

    def test_missing_external_dir_is_a_silent_no_op(self, tmp_path):
        catalog = build_default_skill_catalog(external_dir=tmp_path / "does-not-exist")
        assert catalog.get("research") is not None
        assert catalog.get("valuation") is not None


class TestSkillDispatcher:
    def _catalog(self) -> SkillCatalog:
        catalog = SkillCatalog()
        catalog.register(SkillManifest(name="research", body=""))
        catalog.register(SkillManifest(name="valuation", body="Valuation guidance."))
        return catalog

    def test_resolves_known_skill_with_body(self):
        dispatcher = SkillDispatcher(self._catalog())
        manifest = dispatcher.resolve("valuation")
        assert manifest is not None
        assert manifest.name == "valuation"
        assert manifest.body == "Valuation guidance."

    def test_resolves_known_structural_skill_with_empty_body(self):
        dispatcher = SkillDispatcher(self._catalog())
        manifest = dispatcher.resolve("research")
        assert manifest is not None
        assert manifest.body == ""

    def test_unknown_name_resolves_to_none(self):
        dispatcher = SkillDispatcher(self._catalog())
        assert dispatcher.resolve("does-not-exist") is None

    def test_none_and_empty_string_resolve_to_none(self):
        dispatcher = SkillDispatcher(self._catalog())
        assert dispatcher.resolve(None) is None
        assert dispatcher.resolve("") is None

    def test_strips_surrounding_whitespace(self):
        dispatcher = SkillDispatcher(self._catalog())
        manifest = dispatcher.resolve("  valuation  ")
        assert manifest is not None
        assert manifest.name == "valuation"

    def test_resolves_against_real_default_catalog(self):
        # Locks in the actual app-level wiring: both the seeded structural
        # skill and the shipped builtin must resolve through one dispatcher.
        dispatcher = SkillDispatcher(build_default_skill_catalog())

        valuation = dispatcher.resolve("valuation")
        assert valuation is not None
        assert "估值结论" in valuation.body

        research = dispatcher.resolve("research")
        assert research is not None
        assert research.body == ""

        assert dispatcher.resolve("not-a-real-skill") is None


class TestSkillInstaller:
    def _content(self, name: str = "demo", body: str = "Body.") -> str:
        return f"---\nname: {name}\ndescription: Demo\n---\n{body}"

    def test_install_from_content_writes_and_overwrites(self, tmp_path):
        ext = tmp_path / "skills"
        result = skill_installer.install_from_content(
            self._content(name="alpha", body="First."), None, ext
        )
        assert result.name == "alpha"
        assert result.overwritten is False
        target = ext / "alpha" / SKILL_FILENAME
        assert target.is_file()
        assert "First." in target.read_text(encoding="utf-8")

        # Re-installing the same name overwrites in place and is flagged as such.
        again = skill_installer.install_from_content(
            self._content(name="alpha", body="Second."), None, ext
        )
        assert again.overwritten is True
        assert "Second." in target.read_text(encoding="utf-8")

    def test_frontmatter_name_wins_over_hint(self, tmp_path):
        ext = tmp_path / "skills"
        result = skill_installer.install_from_content(
            self._content(name="real"), "hint-name", ext
        )
        assert result.name == "real"
        assert (ext / "real" / SKILL_FILENAME).is_file()
        assert not (ext / "hint-name").exists()

    def test_hint_used_when_frontmatter_has_no_name(self, tmp_path):
        ext = tmp_path / "skills"
        result = skill_installer.install_from_content(
            "Just a body, no frontmatter.", "my-hint", ext
        )
        assert result.name == "my-hint"
        assert (ext / "my-hint" / SKILL_FILENAME).is_file()

    def test_atomic_write_leaves_no_temp_files(self, tmp_path):
        ext = tmp_path / "skills"
        skill_installer.install_from_content(self._content(name="clean"), None, ext)
        # The temp file must have been renamed into place, not left behind.
        assert [p.name for p in (ext / "clean").iterdir()] == [SKILL_FILENAME]

    def test_rejects_path_traversal_and_invalid_names(self, tmp_path):
        ext = tmp_path / "skills"
        for bad in ["../evil", "a/b", "..", "with space", "dot.name", "name/../x", ""]:
            with pytest.raises(skill_installer.SkillInstallError):
                skill_installer.install_from_content("body", bad, ext)
        # Nothing escaped the external pool.
        assert not (tmp_path / "evil").exists()
        assert not ext.exists() or list(ext.iterdir()) == []

    def test_rejects_overlong_name(self, tmp_path):
        with pytest.raises(skill_installer.SkillInstallError):
            skill_installer.install_from_content("body", "x" * 65, tmp_path / "skills")

    def test_rejects_empty_content(self, tmp_path):
        with pytest.raises(skill_installer.SkillInstallError):
            skill_installer.install_from_content("   ", "demo", tmp_path / "skills")

    def test_install_from_url_rejects_non_http_scheme(self, tmp_path):
        for url in ["file:///etc/passwd", "ftp://host/x", "/local/path"]:
            with pytest.raises(skill_installer.SkillInstallError):
                skill_installer.install_from_url(url, tmp_path / "skills")

    def test_install_from_url_downloads_and_installs(self, tmp_path):
        ext = tmp_path / "skills"
        payload = self._content(name="downloaded", body="Remote body.").encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            result = skill_installer.install_from_url(
                "https://example.com/skills/downloaded/SKILL.md", ext
            )
        assert result.name == "downloaded"
        assert "Remote body." in (ext / "downloaded" / SKILL_FILENAME).read_text("utf-8")

    def test_install_from_url_rejects_oversize(self, tmp_path):
        big = b"x" * (skill_installer.MAX_SKILL_BYTES + 1)
        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(big)):
            with pytest.raises(skill_installer.SkillInstallError):
                skill_installer.install_from_url(
                    "https://example.com/big.md", tmp_path / "skills"
                )

    def test_uninstall_removes_external(self, tmp_path):
        ext = tmp_path / "skills"
        skill_installer.install_from_content(self._content(name="temp"), None, ext)
        removed = skill_installer.uninstall("temp", ext, BUILTIN_SKILLS_DIR)
        assert removed == "temp"
        assert not (ext / "temp").exists()

    def test_uninstall_rejects_builtin(self, tmp_path):
        # 'valuation' ships under BUILTIN_SKILLS_DIR and must never be deletable.
        with pytest.raises(PermissionError):
            skill_installer.uninstall("valuation", tmp_path / "skills", BUILTIN_SKILLS_DIR)

    def test_uninstall_missing_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            skill_installer.uninstall("ghost", tmp_path / "skills", BUILTIN_SKILLS_DIR)

    def test_uninstall_rejects_traversal_name(self, tmp_path):
        with pytest.raises(skill_installer.SkillInstallError):
            skill_installer.uninstall("../evil", tmp_path / "skills", BUILTIN_SKILLS_DIR)

    def test_derive_name_from_url(self):
        derive = skill_installer._derive_name_from_url
        assert derive("https://x.com/skills/foo/SKILL.md") == "foo"
        assert derive("https://x.com/bar.md") == "bar"
        assert derive("https://x.com/baz") == "baz"
        assert derive("https://x.com/") is None
