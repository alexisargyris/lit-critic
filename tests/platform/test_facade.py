"""Tests for PlatformFacade orchestration helpers."""

from pathlib import Path

from contracts.v1.schemas import FindingContract
from lit_platform.facade import PlatformFacade


class _FakeCoreClient:
    def __init__(self):
        self.last_analyze = None
        self.last_discuss = None

    def analyze(self, req):
        self.last_analyze = req
        return {"ok": True}

    def discuss(self, req):
        self.last_discuss = req
        return {"ok": True}


def test_load_indexes_from_project_reads_expected_files(tmp_path: Path):
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")
    (tmp_path / "CAST.md").write_text("cast", encoding="utf-8")

    indexes = PlatformFacade.load_indexes_from_project(tmp_path)

    assert indexes.CANON == "canon"
    assert indexes.CAST == "cast"
    assert indexes.GLOSSARY is None


def test_load_scene_text_reads_file(tmp_path: Path):
    scene = tmp_path / "scene.md"
    scene.write_text("Once upon a test.", encoding="utf-8")

    loaded = PlatformFacade.load_scene_text(scene)

    assert loaded == "Once upon a test."


def test_load_legacy_indexes_from_project_uses_md_keys_and_optional_files(tmp_path: Path):
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")
    (tmp_path / "LEARNING.md").write_text("learned", encoding="utf-8")

    indexes = PlatformFacade.load_legacy_indexes_from_project(
        tmp_path,
        optional_filenames=("LEARNING.md",),
    )

    assert indexes["CANON.md"] == "canon"
    assert indexes["CAST.md"] == ""
    assert indexes["LEARNING.md"] == "learned"


def test_discuss_finding_uses_condensed_context():
    core = _FakeCoreClient()
    facade = PlatformFacade(core_client=core)

    finding = FindingContract(
        number=1,
        severity="major",
        lens="prose",
        location="Paragraph 1",
        evidence="Repeated starts",
        impact="Monotony",
        options=["Vary openings"],
        flagged_by=["prose"],
    )

    facade.discuss_finding(
        scene_text="Scene",
        finding=finding,
        author_message="Intentional rhythm",
        discussion_turns=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ],
        discussion_model="gpt-4o",
        api_keys={"openai": "sk-openai-test"},
        max_tokens=512,
    )

    assert core.last_discuss is not None
    assert core.last_discuss.discussion_context["turn_count"] == 2
