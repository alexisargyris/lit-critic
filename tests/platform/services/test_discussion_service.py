"""Tests for lit_platform.services.discussion_service scene scoping behavior."""

from lit_platform.runtime.models import Finding
from lit_platform.services import discussion_service


class TestDiscussionSceneResolution:
    def test_resolve_finding_scene_content_uses_finding_scene_file(self, sample_session_state, temp_project_dir):
        scene_file = temp_project_dir / "chapter02.md"
        scene_file.write_text("Scoped scene text", encoding="utf-8")

        finding = Finding(number=1, severity="major", lens="prose", location="P1", scene_path=str(scene_file))
        text = discussion_service._resolve_finding_scene_content(sample_session_state, finding)

        assert text == "Scoped scene text"

    def test_resolve_finding_scene_content_falls_back_to_session_content(self, sample_session_state):
        finding = Finding(number=1, severity="major", lens="prose", location="P1", scene_path="/missing/scene.md")
        text = discussion_service._resolve_finding_scene_content(sample_session_state, finding)

        assert text == sample_session_state.scene_content
