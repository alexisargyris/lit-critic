"""
Tests for active-session finding-flow routes.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from web.routes import session_mgr
from web.session_manager import ResumeScenePathError
from lit_platform.runtime.models import Finding, SessionState, LearningData


class TestSessionEndpoints:
    """Test session-related API endpoints."""

    def test_get_session_no_active(self, client, reset_session):
        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

    def test_get_finding_no_session(self, client, reset_session):
        response = client.get("/api/finding")
        assert response.status_code == 404

    def test_continue_no_session(self, client, reset_session):
        response = client.post("/api/finding/continue")
        assert response.status_code == 404

    def test_accept_no_session(self, client, reset_session):
        response = client.post("/api/finding/accept")
        assert response.status_code == 404

    def test_reject_no_session(self, client, reset_session):
        response = client.post("/api/finding/reject", json={"reason": "test"})
        assert response.status_code == 404

    def test_discuss_no_session(self, client, reset_session):
        response = client.post("/api/finding/discuss", json={"message": "test"})
        assert response.status_code == 404

    def test_save_learning_no_active(self, client, reset_session):
        response = client.post("/api/learning/save")
        assert response.status_code == 404

    def test_review_no_session(self, client, reset_session):
        response = client.post("/api/finding/review")
        assert response.status_code == 404

    def test_skip_to_invalid_lens(self, client, reset_session):
        response = client.post("/api/finding/skip-to/invalid")
        assert response.status_code == 400

    def test_skip_to_no_session(self, client, reset_session):
        response = client.post("/api/finding/skip-to/structure")
        assert response.status_code == 404

    def test_ambiguity_no_session(self, client, reset_session):
        response = client.post("/api/finding/ambiguity", json={"intentional": True})
        assert response.status_code == 404

    def test_goto_no_session(self, client, reset_session):
        response = client.post("/api/finding/goto", json={"index": 0})
        assert response.status_code == 404


class TestWithActiveSession:
    """Test endpoints with an active session (mocked)."""

    @pytest.fixture
    def active_session(self, reset_session):
        """Set up a mock active session with findings."""
        mock_client = MagicMock()
        learning = LearningData()

        findings = [
            Finding(
                number=1, severity="critical", lens="prose",
                location="Paragraph 1", evidence="Test evidence 1",
                impact="Test impact 1", options=["Fix it", "Leave it"],
                flagged_by=["prose"]
            ),
            Finding(
                number=2, severity="major", lens="structure",
                location="Paragraph 5", evidence="Test evidence 2",
                impact="Test impact 2", options=["Restructure"],
                flagged_by=["structure"]
            ),
            Finding(
                number=3, severity="minor", lens="clarity",
                location="Paragraph 10", evidence="Test evidence 3",
                impact="Test impact 3", options=["Clarify"],
                flagged_by=["clarity"],
                ambiguity_type="ambiguous_possibly_intentional"
            ),
            Finding(
                number=4, severity="major", lens="dialogue",
                location="Paragraph 12", evidence="Dialogue voices blend",
                impact="Weakens character distinction", options=["Differentiate diction"],
                flagged_by=["dialogue"]
            ),
        ]

        session_mgr.state = SessionState(
            client=mock_client,
            scene_content="Test scene content",
            scene_path="/test/scene.txt",
            project_path=Path("/test/project"),
            indexes={},
            scene_paths=["/test/scene.txt", "/test/scene-2.txt"],
            learning=learning,
            findings=findings,
        )
        session_mgr.current_index = 0

    def test_get_session_active(self, client, active_session):
        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["total_findings"] == 4
        assert data["scene_paths"] == ["/test/scene.txt", "/test/scene-2.txt"]

    def test_session_includes_model_info(self, client, active_session):
        """Session summary includes model name, id, and label."""
        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data
        model = data["model"]
        assert "name" in model
        assert "id" in model
        assert "label" in model
        # Default model should be sonnet (from SessionState default)
        assert model["name"] == "sonnet"

    def test_get_current_finding(self, client, active_session):
        response = client.get("/api/finding")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 1
        assert data["finding"]["severity"] == "critical"
        assert data["finding"]["origin"] == "legacy"
        assert data["current"] == 1
        assert data["total"] == 4

    def test_continue_finding(self, client, active_session):
        response = client.post("/api/finding/continue")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 2
        assert data["finding"]["origin"] == "legacy"

    def test_accept_finding(self, client, active_session):
        response = client.post("/api/finding/accept")
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "accepted"
        assert data["action"]["finding_number"] == 1
        assert data["next"]["complete"] is False
        assert data["next"]["finding"]["number"] == 2
        assert data["next"]["finding"]["origin"] == "legacy"

    def test_reject_finding(self, client, active_session):
        response = client.post("/api/finding/reject", json={"reason": "Style choice"})
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "rejected"
        assert data["action"]["finding_number"] == 1
        assert data["next"]["complete"] is False

    def test_reject_finding_empty_reason(self, client, active_session):
        response = client.post("/api/finding/reject", json={"reason": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "rejected"

    def test_review_finding(self, client, active_session):
        response = client.post("/api/finding/review")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 1
        assert "review" in data

    def test_review_does_not_report_complete_when_pending_findings_remain(self, client, active_session):
        """Review should recover to unresolved findings instead of false completion."""
        # Simulate being on a withdrawn tail finding while earlier findings are pending.
        session_mgr.current_index = 3
        session_mgr.state.findings[3].status = 'withdrawn'

        response = client.post("/api/finding/review")
        assert response.status_code == 200
        data = response.json()

        assert data["complete"] is False
        assert data["message"] == "There are still pending findings to review."
        assert data["finding"]["number"] == 1
        assert data["current"] == 1
        assert session_mgr.current_index == 0
        assert "review" in data

    def test_skip_to_structure(self, client, active_session):
        response = client.post("/api/finding/skip-to/structure")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["lens"] == "structure"

    def test_skip_to_coherence(self, client, active_session):
        response = client.post("/api/finding/skip-to/coherence")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        # clarity is a coherence lens
        assert data["finding"]["lens"] == "clarity"

    def test_mark_ambiguity_intentional(self, client, active_session):
        # Move to finding #3 (the ambiguity one)
        session_mgr.current_index = 2
        response = client.post("/api/finding/ambiguity", json={"intentional": True})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "marked_intentional"

    def test_mark_ambiguity_accidental(self, client, active_session):
        session_mgr.current_index = 2
        response = client.post("/api/finding/ambiguity", json={"intentional": False})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "marked_accidental"

    def test_goto_finding(self, client, active_session):
        """Goto jumps to a specific finding by index."""
        response = client.post("/api/finding/goto", json={"index": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 3
        assert data["finding"]["lens"] == "clarity"
        assert data["current"] == 3
        assert data["total"] == 4
        # Backend index should have been updated
        assert session_mgr.current_index == 2

    def test_skip_to_coherence_can_land_on_dialogue(self, client, active_session):
        # Start from clarity so next coherence lens is dialogue
        session_mgr.current_index = 2
        response = client.post("/api/finding/skip-to/coherence")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["lens"] == "dialogue"

    def test_goto_finding_first(self, client, active_session):
        """Goto to index 0 returns the first finding."""
        session_mgr.current_index = 2  # start elsewhere
        response = client.post("/api/finding/goto", json={"index": 0})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 1
        assert session_mgr.current_index == 0

    def test_goto_finding_out_of_range(self, client, active_session):
        """Goto with out-of-range index returns complete."""
        response = client.post("/api/finding/goto", json={"index": 99})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is True

    def test_goto_finding_negative_index(self, client, active_session):
        """Goto with negative index returns complete."""
        response = client.post("/api/finding/goto", json={"index": -1})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is True

    def test_goto_withdrawn_finding(self, client, active_session):
        """Goto a withdrawn finding is still navigable and returns full state."""
        session_mgr.state.findings[1].status = 'withdrawn'
        session_mgr.state.findings[1].discussion_turns = [
            {"role": "user", "content": "This is intentional."},
            {"role": "assistant", "content": "Understood; withdrawing."},
        ]

        response = client.post("/api/finding/goto", json={"index": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 2
        assert data["finding"]["status"] == "withdrawn"
        assert len(data["finding"]["discussion_turns"]) == 2
        assert data["finding"]["discussion_turns"][0]["role"] == "user"

    def test_goto_then_accept(self, client, active_session):
        """After goto, accept operates on the correct finding."""
        # Jump to finding #2 (index 1)
        client.post("/api/finding/goto", json={"index": 1})
        assert session_mgr.current_index == 1

        # Accept should target finding #2
        response = client.post("/api/finding/accept")
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "accepted"
        assert data["action"]["finding_number"] == 2

    def test_goto_then_reject(self, client, active_session):
        """After goto, reject operates on the correct finding."""
        client.post("/api/finding/goto", json={"index": 2})
        assert session_mgr.current_index == 2

        response = client.post("/api/finding/reject", json={"reason": "Not relevant"})
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "rejected"
        assert data["action"]["finding_number"] == 3

    def test_get_scene_content(self, client, active_session):
        response = client.get("/api/scene")
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test scene content"

    def test_continue_past_all_findings(self, client, active_session):
        # Move past all findings
        session_mgr.current_index = 3
        response = client.post("/api/finding/continue")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["message"] == "There are still pending findings to review."
        assert data["finding"]["number"] == 1

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding(self, mock_discuss, client, active_session):
        mock_discuss.return_value = ("Good point, I concede.", "conceded")

        response = client.post("/api/finding/discuss", json={"message": "This is intentional"})
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Good point, I concede."
        assert data["status"] == "conceded"
        assert data["finding_status"] == "withdrawn"

    @patch("web.session_manager.handle_discussion_stream")
    def test_discuss_stream_conceded_maps_to_withdrawn(self, mock_stream, client, active_session):
        """Streaming endpoint should canonicalize conceded to withdrawn finding status."""
        async def _mock_gen(state, finding, msg):
            yield ("token", "Fair point.")
            yield ("done", {"response": "Fair point.", "status": "conceded"})
        mock_stream.side_effect = lambda state, finding, msg, **kw: _mock_gen(state, finding, msg)

        response = client.post("/api/finding/discuss/stream", json={"message": "This is intentional"})
        assert response.status_code == 200

        body = response.text
        events = []
        for line in body.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        done = [e for e in events if e["type"] == "done"][0]
        assert done["status"] == "conceded"
        assert done["finding_status"] == "withdrawn"

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding_accepted(self, mock_discuss, client, active_session):
        mock_discuss.return_value = ("Glad you agree!", "accepted")

        response = client.post("/api/finding/discuss", json={"message": "You're right, I'll fix it"})
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Glad you agree!"
        assert data["status"] == "accepted"
        assert data["finding_status"] == "accepted"

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding_continue(self, mock_discuss, client, active_session):
        mock_discuss.return_value = ("Let me explain further.", "continue")

        response = client.post("/api/finding/discuss", json={"message": "I'm not sure about this"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "continue"
        assert data["finding_status"] == "pending"

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding_revised(self, mock_discuss, client, active_session):
        """Phase 2: Revised finding returns updated finding data."""
        finding = session_mgr.state.findings[0]
        finding.revision_history = [{"version": 1, "severity": "critical"}]
        mock_discuss.return_value = ("I've revised the severity.", "revised")

        response = client.post("/api/finding/discuss", json={"message": "That seems too harsh"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revised"
        assert data["finding_status"] == "revised"
        assert "finding" in data
        assert "revision_history" in data

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding_withdrawn(self, mock_discuss, client, active_session):
        """Phase 2: Withdrawn finding returns updated finding data."""
        mock_discuss.return_value = ("You're right, I'm withdrawing this.", "withdrawn")

        response = client.post("/api/finding/discuss", json={"message": "This doesn't apply here"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "withdrawn"
        assert data["finding_status"] == "withdrawn"
        assert "finding" in data

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding_escalated(self, mock_discuss, client, active_session):
        """Phase 2: Escalated finding returns updated finding data with revision history."""
        finding = session_mgr.state.findings[0]
        finding.revision_history = [{"version": 1, "severity": "major"}]
        mock_discuss.return_value = ("Actually this is worse than I thought.", "escalated")

        response = client.post("/api/finding/discuss", json={"message": "Wait, there's more context"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "escalated"
        assert data["finding_status"] == "escalated"
        assert "finding" in data
        assert "revision_history" in data

    def test_discuss_stream_no_session(self, client, reset_session):
        response = client.post("/api/finding/discuss/stream", json={"message": "test"})
        assert response.status_code == 404

    @patch("web.session_manager.handle_discussion_stream")
    def test_discuss_stream_returns_sse(self, mock_stream, client, active_session):
        """Streaming discuss endpoint returns SSE content-type."""
        async def _mock_gen(state, finding, msg):
            yield ("token", "Hello ")
            yield ("token", "world.")
            yield ("done", {"response": "Hello world.", "status": "continue"})
        mock_stream.side_effect = lambda state, finding, msg, **kw: _mock_gen(state, finding, msg)

        response = client.post("/api/finding/discuss/stream", json={"message": "test"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    @patch("web.session_manager.handle_discussion_stream")
    def test_discuss_stream_yields_tokens_then_done(self, mock_stream, client, active_session):
        """Streaming endpoint yields token events followed by done event."""
        async def _mock_gen(state, finding, msg):
            yield ("token", "Good ")
            yield ("token", "point.")
            yield ("done", {"response": "Good point.", "status": "continue"})
        mock_stream.side_effect = lambda state, finding, msg, **kw: _mock_gen(state, finding, msg)

        response = client.post("/api/finding/discuss/stream", json={"message": "test"})
        assert response.status_code == 200

        # Parse SSE events from response body
        body = response.text
        events = []
        for line in body.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        # Should have 2 token events + 1 done event
        token_events = [e for e in events if e["type"] == "token"]
        done_events = [e for e in events if e["type"] == "done"]
        assert len(token_events) == 2
        assert token_events[0]["text"] == "Good "
        assert token_events[1]["text"] == "point."
        assert len(done_events) == 1
        assert done_events[0]["response"] == "Good point."
        assert done_events[0]["status"] == "continue"

    @patch("web.session_manager.handle_discussion_stream")
    def test_discuss_stream_applies_finding_status(self, mock_stream, client, active_session):
        """Streaming endpoint applies finding status on done."""
        async def _mock_gen(state, finding, msg):
            yield ("token", "Accepted.")
            yield ("done", {"response": "Accepted.", "status": "accepted"})
        mock_stream.side_effect = lambda state, finding, msg, **kw: _mock_gen(state, finding, msg)

        response = client.post("/api/finding/discuss/stream", json={"message": "I'll fix it"})
        assert response.status_code == 200

        body = response.text
        events = []
        for line in body.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        done = [e for e in events if e["type"] == "done"][0]
        assert done["status"] == "accepted"
        assert done["finding_status"] == "accepted"


class TestCheckSession:
    """Test the check-session endpoint."""

    def test_check_nonexistent_project(self, client, reset_session):
        response = client.post("/api/check-session", json={
            "project_path": "/nonexistent/path/that/does/not/exist"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False

    @patch("web.session_manager.check_active_session")
    def test_check_existing_session(self, mock_check, client, reset_session, tmp_path):
        mock_check.return_value = {
            "exists": True,
            "scene_path": str(tmp_path / "scene.txt"),
            "saved_at": "2025-01-01T12:00:00",
            "current_index": 3,
            "total_findings": 5,
        }

        response = client.post("/api/check-session", json={
            "project_path": str(tmp_path)
        })
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["current_index"] == 3
        assert data["total_findings"] == 5


class TestSessionManager:
    """Unit tests for the WebSessionManager."""

    def test_is_active_no_state(self, reset_session):
        assert session_mgr.is_active is False

    def test_total_findings_no_state(self, reset_session):
        assert session_mgr.total_findings == 0

    def test_get_current_finding_no_state(self, reset_session):
        assert session_mgr.get_current_finding() is None

    def test_advance_no_state(self, reset_session):
        # Should return None without error
        result = session_mgr.advance()
        assert result is None

    def test_accept_no_active(self, reset_session):
        result = session_mgr.accept_finding()
        assert "error" in result

    def test_reject_no_active(self, reset_session):
        result = session_mgr.reject_finding("reason")
        assert "error" in result

    def test_mark_ambiguity_no_active(self, reset_session):
        result = session_mgr.mark_ambiguity(True)
        assert "error" in result

    def test_save_no_active(self, reset_session):
        result = session_mgr.save_current_session()
        assert "error" in result

    def test_save_learning_no_active(self, reset_session):
        result = session_mgr.save_learning()
        assert "error" in result

    def test_clear_no_active(self, reset_session):
        result = session_mgr.clear_session()
        assert "error" in result

    def test_goto_finding_no_state(self, reset_session):
        result = session_mgr.goto_finding(0)
        assert result is None

    def test_goto_finding_out_of_range(self, reset_session):
        result = session_mgr.goto_finding(99)
        assert result is None

    @pytest.mark.asyncio
    async def test_start_analysis_maps_global_lines_and_location_to_local_scene(self, reset_session, tmp_path):
        """Multi-scene analysis should remap global lines and location labels to local values."""
        scene1 = tmp_path / "scene1.txt"
        scene2 = tmp_path / "scene2.txt"
        scene1.write_text("A1\nA2", encoding="utf-8")
        scene2.write_text("B1\nB2", encoding="utf-8")

        line_map = [
            {
                "scene_path": str(scene1),
                "scene_name": scene1.name,
                "marker_line": 1,
                "global_start": 2,
                "global_end": 3,
                "local_start": 1,
                "local_end": 2,
            },
            {
                "scene_path": str(scene2),
                "scene_name": scene2.name,
                "marker_line": 5,
                "global_start": 6,
                "global_end": 7,
                "local_start": 1,
                "local_end": 2,
            },
        ]

        async def _fake_lens(*args, **kwargs):
            lens_name = args[1]
            return MagicMock(lens_name=lens_name, error=None)

        coordinated = {
            "findings": [
                {
                    "number": 1,
                    "severity": "major",
                    "lens": "prose",
                    "location": "L006-L007, second scene issue",
                    "line_start": 6,
                    "line_end": 7,
                    "evidence": "Test evidence",
                    "impact": "Test impact",
                    "options": ["Fix"],
                    "flagged_by": ["prose"],
                    "ambiguity_type": None,
                }
            ],
            "glossary_issues": [],
        }

        with patch("web.session_manager.check_active_session", return_value={"exists": False}), \
             patch.object(session_mgr, "_load_project_files", return_value={}), \
             patch.object(session_mgr, "_load_scenes", return_value=("combined", line_map)), \
             patch("web.session_manager.load_learning", return_value=LearningData()), \
             patch("web.session_manager.generate_learning_markdown", return_value=""), \
             patch("web.session_manager.create_client", return_value=MagicMock()), \
             patch.object(session_mgr, "_run_lens_with_progress", side_effect=_fake_lens), \
             patch("web.session_manager.run_coordinator_chunked", new=AsyncMock(return_value=coordinated)), \
             patch("web.session_manager.create_session", return_value=1):
            await session_mgr.start_analysis(
                scene_path=str(scene1),
                project_path=str(tmp_path),
                api_key="sk-ant-explicit",
                scene_paths=[str(scene1), str(scene2)],
            )

        # Code checks run first and may prepend deterministic findings.
        # Assert remapping on the coordinated prose finding specifically.
        finding = next(f for f in session_mgr.state.findings if f.lens == "prose")
        assert finding.scene_path == str(scene2)
        assert finding.line_start == 1
        assert finding.line_end == 2
        assert finding.location == "L1-L2, second scene issue"

    @pytest.mark.asyncio
    async def test_start_analysis_dispatches_lenses_by_tier_model(self, reset_session, tmp_path):
        """Frontier lenses should use frontier model/client; others should use checker model/client."""
        from lit_platform.runtime.config import resolve_model

        scene = tmp_path / "scene.txt"
        scene.write_text("A1\nA2", encoding="utf-8")

        checker_client = MagicMock(name="checker_client")
        frontier_client = MagicMock(name="frontier_client")

        async def _fake_lens(*args, **kwargs):
            return SimpleNamespace(lens_name=args[1], error=None)

        coordinated = {"findings": [], "glossary_issues": []}

        with patch("web.session_manager.check_active_session", return_value={"exists": False}), \
             patch.object(session_mgr, "_load_project_files", return_value={}), \
             patch.object(session_mgr, "_load_scenes", return_value=("combined", [])), \
             patch("web.session_manager.load_learning", return_value=LearningData()), \
             patch("web.session_manager.generate_learning_markdown", return_value=""), \
             patch("web.session_manager.create_client", side_effect=[checker_client, frontier_client]), \
             patch.object(session_mgr, "_run_lens_with_progress", new=AsyncMock(side_effect=_fake_lens)) as mock_run_lens, \
             patch("web.session_manager.run_coordinator_chunked", new=AsyncMock(return_value=coordinated)) as mock_coord, \
             patch("web.session_manager.create_session", return_value=1):
            await session_mgr.start_analysis(
                scene_path=str(scene),
                project_path=str(tmp_path),
                api_key="sk-openai-explicit",
                model="gpt-4o",
                discussion_model="sonnet",
                discussion_api_key="sk-ant-explicit",
                scene_paths=[str(scene)],
            )

        assert mock_run_lens.await_count == 7

        frontier_expected_model = resolve_model("sonnet")["id"]
        checker_expected_model = resolve_model("gpt-4o")["id"]
        frontier_lenses = {"prose", "structure", "horizon"}

        by_lens = {call.args[1]: call for call in mock_run_lens.await_args_list}
        assert set(by_lens.keys()) == {
            "prose", "structure", "logic", "clarity", "continuity", "dialogue", "horizon"
        }

        for lens_name, call in by_lens.items():
            if lens_name in frontier_lenses:
                assert call.args[0] is frontier_client
                assert call.kwargs["model"] == frontier_expected_model
            else:
                assert call.args[0] is checker_client
                assert call.kwargs["model"] == checker_expected_model

        _, coord_kwargs = mock_coord.await_args
        assert coord_kwargs["model"] == checker_expected_model


