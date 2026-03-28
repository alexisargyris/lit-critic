"""Tests for lit_platform.services.discussion_service scene scoping behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from lit_platform.runtime.models import Finding
from lit_platform.services import discussion_service
from lit_platform.services.analysis_service import resolve_model


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


@pytest.mark.asyncio
async def test_discuss_finding_uses_frontier_model_id(sample_session_state):
    finding = Finding(number=1, severity="major", lens="prose", location="P1")
    sample_session_state.findings = [finding]
    sample_session_state.frontier_model = "haiku"
    sample_session_state.discussion_model = "gpt-4o"
    sample_session_state.discussion_client = MagicMock()
    sample_session_state.discussion_client.create_message = AsyncMock(
        return_value=MagicMock(text="[CONTINUE] ack")
    )

    response_text, status = await discussion_service.discuss_finding(
        sample_session_state,
        finding,
        "please review",
    )

    assert status == "continue"
    assert "ack" in response_text
    assert sample_session_state.discussion_client.create_message.call_args.kwargs["model"] == resolve_model("haiku")["id"]
