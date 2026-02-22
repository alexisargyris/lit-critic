"""
Tests for the lit-critic Web UI.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from fastapi.testclient import TestClient
from fastapi import HTTPException

from web.app import app
from web.routes import session_mgr
from web.session_manager import ResumeScenePathError
from lit_platform.runtime.models import Finding, SessionState, LearningData


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def reset_session():
    """Reset the shared session manager between tests."""
    session_mgr.state = None
    session_mgr.results = None
    session_mgr.current_index = 0
    session_mgr.analysis_progress = None
    yield
    session_mgr.state = None
    session_mgr.results = None
    session_mgr.current_index = 0
    session_mgr.analysis_progress = None


class TestIndexPage:
    """Test the main page serves correctly."""

    def test_index_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "lit-critic" in response.text


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
        assert data["total_findings"] == 3
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
        assert data["current"] == 1
        assert data["total"] == 3

    def test_continue_finding(self, client, active_session):
        response = client.post("/api/finding/continue")
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["finding"]["number"] == 2

    def test_accept_finding(self, client, active_session):
        response = client.post("/api/finding/accept")
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["status"] == "accepted"
        assert data["action"]["finding_number"] == 1
        assert data["next"]["complete"] is False
        assert data["next"]["finding"]["number"] == 2

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
        session_mgr.current_index = 2
        session_mgr.state.findings[2].status = 'withdrawn'

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
        assert data["total"] == 3
        # Backend index should have been updated
        assert session_mgr.current_index == 2

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
        session_mgr.current_index = 2
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


class TestConfigEndpoint:
    """Test the /api/config endpoint."""

    def test_config_no_api_key(self, client):
        """Config reports no key when env vars are unset."""
        import os
        anthropic_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
        openai_backup = os.environ.pop("OPENAI_API_KEY", None)
        try:
            response = client.get("/api/config")
            assert response.status_code == 200
            assert response.json()["api_key_configured"] is False
        finally:
            if anthropic_backup:
                os.environ["ANTHROPIC_API_KEY"] = anthropic_backup
            if openai_backup:
                os.environ["OPENAI_API_KEY"] = openai_backup

    def test_config_with_api_key(self, client):
        """Config reports key present when env var is set."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            response = client.get("/api/config")
            assert response.status_code == 200
            assert response.json()["api_key_configured"] is True

    def test_config_returns_available_models(self, client):
        """Config returns available models with labels."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "available_models" in data
        assert "default_model" in data
        # All expected models are present
        models = data["available_models"]
        assert "sonnet" in models
        assert "opus" in models
        assert "haiku" in models
        # Each model has a label
        for name, info in models.items():
            assert "label" in info, f"Model '{name}' missing label"

    def test_config_default_model_is_valid(self, client):
        """Default model must be one of the available models."""
        response = client.get("/api/config")
        data = response.json()
        assert data["default_model"] in data["available_models"]

    def test_config_models_include_provider(self, client):
        """Each model in config should include its provider."""
        response = client.get("/api/config")
        data = response.json()
        for name, info in data["available_models"].items():
            assert "provider" in info, f"Model '{name}' missing provider"
            assert info["provider"] in ("anthropic", "openai")

    def test_config_includes_openai_models(self, client):
        """Config should include at least one OpenAI model."""
        response = client.get("/api/config")
        data = response.json()
        openai_models = [n for n, i in data["available_models"].items() if i["provider"] == "openai"]
        assert len(openai_models) >= 1

    def test_config_reports_per_provider_keys(self, client):
        """Config should report api_keys_configured per provider."""
        response = client.get("/api/config")
        data = response.json()
        assert "api_keys_configured" in data
        assert "anthropic" in data["api_keys_configured"]
        assert "openai" in data["api_keys_configured"]

    def test_config_openai_key_detection(self, client):
        """Config should detect OPENAI_API_KEY when set."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-oai"}):
            response = client.get("/api/config")
            data = response.json()
            assert data["api_keys_configured"]["openai"] is True


class TestRepoPreflightEndpoints:
    """Test repo-path preflight status and update routes."""

    @patch("web.routes.get_repo_path")
    @patch("web.routes.validate_repo_path")
    def test_repo_preflight_returns_status_payload(self, mock_validate, mock_get_repo_path, client):
        mock_get_repo_path.return_value = "C:/invalid/path"
        mock_validate.return_value = type("Result", (), {
            "ok": False,
            "reason_code": "not_found",
            "message": "Repository path was not found",
            "path": "C:/invalid/path",
        })()

        response = client.get("/api/repo-preflight")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["reason_code"] == "not_found"
        assert payload["configured_path"] == "C:/invalid/path"
        assert "marker" in payload

    @patch("web.routes.set_repo_path")
    @patch("web.routes.validate_repo_path")
    @patch("web.routes.get_repo_path")
    def test_repo_path_update_persists_when_valid(
        self,
        mock_get_repo_path,
        mock_validate,
        mock_set_repo_path,
        client,
    ):
        valid_input = "C:/lit-critic"
        mock_get_repo_path.return_value = valid_input
        mock_validate.side_effect = [
            type("Result", (), {
                "ok": True,
                "reason_code": "",
                "message": "Repository path is valid.",
                "path": valid_input,
            })(),
            type("Result", (), {
                "ok": True,
                "reason_code": "",
                "message": "Repository path is valid.",
                "path": valid_input,
            })(),
        ]

        response = client.post("/api/repo-path", json={"repo_path": valid_input})
        assert response.status_code == 200
        mock_set_repo_path.assert_called_once_with(valid_input)
        assert response.json()["ok"] is True

    @patch("web.routes.validate_repo_path")
    def test_repo_path_update_rejects_invalid(self, mock_validate, client):
        mock_validate.return_value = type("Result", (), {
            "ok": False,
            "reason_code": "missing_marker",
            "message": "Repository directory does not contain lit-critic-web.py",
            "path": "C:/somewhere",
        })()

        response = client.post("/api/repo-path", json={"repo_path": "C:/somewhere"})
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "repo_path_invalid"
        assert detail["reason_code"] == "missing_marker"

    @patch("web.routes._ensure_repo_preflight_ready")
    def test_analyze_blocks_when_repo_preflight_invalid(self, mock_preflight, client, reset_session):
        mock_preflight.side_effect = HTTPException(
            status_code=409,
            detail={"code": "repo_path_invalid", "message": "invalid repo path"},
        )

        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "repo_path_invalid"


class TestAnalyzeEndpoint:
    """Test the analyze endpoint."""

    @pytest.fixture(autouse=True)
    def _repo_preflight_ok(self, monkeypatch):
        monkeypatch.setattr("web.routes._ensure_repo_preflight_ready", lambda: None)

    def test_analyze_no_api_key(self, client, reset_session):
        """Test analyze fails without API key when env var is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            import os
            env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                response = client.post("/api/analyze", json={
                    "scene_path": "/some/scene.txt",
                    "project_path": "/some/project",
                })
                assert response.status_code == 400
                assert "API key" in response.json()["detail"]
            finally:
                if env_backup:
                    os.environ["ANTHROPIC_API_KEY"] = env_backup

    def test_analyze_nonexistent_project(self, client, reset_session):
        response = client.post("/api/analyze", json={
            "scene_path": "/nonexistent/scene.txt",
            "project_path": "/nonexistent/project",
            "api_key": "test-key",
        })
        assert response.status_code == 404

    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_analyze_accepts_scene_paths_payload(self, mock_start, client, reset_session):
        mock_start.return_value = {"ok": True}

        response = client.post("/api/analyze", json={
            "scene_paths": ["/any/scene1.txt", "/any/scene2.txt"],
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 200
        _, kwargs = mock_start.await_args
        assert kwargs["scene_paths"] == ["/any/scene1.txt", "/any/scene2.txt"]

    def test_analyze_requires_scene_path_or_scene_paths(self, client, reset_session):
        response = client.post("/api/analyze", json={
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 400
        assert response.json()["detail"] == "scene_path or scene_paths is required"

    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_analyze_cross_provider_uses_separate_keys(self, mock_start, client, reset_session):
        """Cross-provider analyze should resolve and pass separate provider keys."""
        mock_start.return_value = {"ok": True}

        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "model": "sonnet",            # anthropic
            "discussion_model": "gpt-4o",  # openai
            "api_key": "sk-ant-explicit",
            "discussion_api_key": "sk-openai-explicit",
        })

        assert response.status_code == 200
        mock_start.assert_awaited_once()
        _, kwargs = mock_start.await_args
        assert kwargs["model"] == "sonnet"
        assert kwargs["discussion_model"] == "gpt-4o"
        assert kwargs["discussion_api_key"] == "sk-openai-explicit"

    def test_analyze_cross_provider_missing_second_key_returns_400(self, client, reset_session):
        """Cross-provider analyze should fail early if discussion provider key is missing."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-env"}, clear=True):
            response = client.post("/api/analyze", json={
                "scene_path": "/any/scene.txt",
                "project_path": "/any/project",
                "model": "sonnet",            # anthropic
                "discussion_model": "gpt-4o",  # openai
            })

        assert response.status_code == 400
        assert "No API key for provider 'openai'" in response.json()["detail"]

    def test_analyze_provider_key_mismatch_returns_400(self, client, reset_session):
        """OpenAI model with Anthropic key should fail with a clear validation error."""
        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "model": "gpt-4o",
            "api_key": "sk-ant-mismatch",
        })

        assert response.status_code == 400
        assert "appears to be an Anthropic key" in response.json()["detail"]

    def test_resume_no_session(self, client, reset_session, tmp_path):
        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "test-key",
        })
        assert response.status_code == 404

    @patch("web.routes.check_active_session")
    @patch.object(session_mgr, "resume_session", new_callable=AsyncMock)
    def test_resume_cross_provider_missing_second_key_returns_400(
        self,
        mock_resume,
        mock_check_active,
        client,
        reset_session,
        tmp_path,
    ):
        """Cross-provider resume should fail early when discussion provider key is missing."""
        mock_check_active.return_value = {
            "exists": True,
            "model": "sonnet",             # anthropic
            "discussion_model": "gpt-4o",  # openai
        }

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-env"}, clear=True):
            response = client.post("/api/resume", json={
                "project_path": str(tmp_path),
            })

        assert response.status_code == 400
        assert "No API key for provider 'openai'" in response.json()["detail"]
        mock_resume.assert_not_awaited()

    @patch("web.routes.check_active_session")
    @patch.object(session_mgr, "resume_session", new_callable=AsyncMock)
    def test_resume_cross_provider_uses_separate_keys(
        self,
        mock_resume,
        mock_check_active,
        client,
        reset_session,
        tmp_path,
    ):
        """Cross-provider resume should resolve and pass both provider keys."""
        mock_check_active.return_value = {
            "exists": True,
            "model": "sonnet",             # anthropic
            "discussion_model": "gpt-4o",  # openai
        }
        mock_resume.return_value = {"active": True}

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant-env",
            "OPENAI_API_KEY": "sk-openai-env",
        }, clear=True):
            response = client.post("/api/resume", json={
                "project_path": str(tmp_path),
            })

        assert response.status_code == 200
        mock_resume.assert_awaited_once_with(
            str(tmp_path),
            "sk-ant-env",
            discussion_api_key="sk-openai-env",
            scene_path_override=None,
        )

    @patch("web.routes.check_active_session")
    @patch.object(session_mgr, "resume_session", new_callable=AsyncMock)
    def test_resume_passes_scene_path_override(
        self,
        mock_resume,
        mock_check_active,
        client,
        reset_session,
        tmp_path,
    ):
        """Resume route should pass scene_path_override through to session manager."""
        mock_check_active.return_value = {"exists": False}
        mock_resume.return_value = {"active": True}

        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "sk-ant-explicit",
            "scene_path_override": str(tmp_path / "renamed_scene.md"),
        })

        assert response.status_code == 200
        mock_resume.assert_awaited_once_with(
            str(tmp_path),
            "sk-ant-explicit",
            discussion_api_key=None,
            scene_path_override=str(tmp_path / "renamed_scene.md"),
        )

    @patch("web.routes.check_active_session")
    @patch.object(session_mgr, "resume_session", new_callable=AsyncMock)
    def test_resume_returns_409_with_structured_detail_for_missing_scene_path(
        self,
        mock_resume,
        mock_check_active,
        client,
        reset_session,
        tmp_path,
    ):
        """Missing saved scene path should return a structured 409 error for recovery UI."""
        mock_check_active.return_value = {"exists": False}
        mock_resume.side_effect = ResumeScenePathError(
            "Saved scene file was not found.",
            saved_scene_path="D:/old-machine/project/ch01.md",
            attempted_scene_path="D:/old-machine/project/ch01.md",
            project_path=str(tmp_path),
            override_provided=False,
        )

        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "scene_path_not_found"
        assert detail["saved_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["attempted_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["project_path"] == str(tmp_path)
        assert detail["override_provided"] is False

    @patch("web.routes._resolve_analysis_and_discussion_keys")
    @patch("web.routes.get_session_detail")
    @patch.object(session_mgr, "resume_session_by_id", new_callable=AsyncMock)
    def test_resume_session_by_id_uses_selected_session_and_returns_summary(
        self,
        mock_resume_by_id,
        mock_get_session_detail,
        mock_resolve_keys,
        client,
        reset_session,
        tmp_path,
    ):
        """POST /api/resume-session should resume the specific selected session id."""
        mock_get_session_detail.return_value = {
            "id": 42,
            "status": "active",
            "model": "sonnet",
            "discussion_model": None,
        }
        mock_resolve_keys.return_value = ("sk-ant-env", None)
        mock_resume_by_id.return_value = {"scene_name": "chapter-01.txt", "total_findings": 5}

        response = client.post("/api/resume-session", json={
            "project_path": str(tmp_path),
            "session_id": 42,
        })

        assert response.status_code == 200
        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 42)
        mock_resume_by_id.assert_awaited_once_with(
            str(tmp_path),
            42,
            "sk-ant-env",
            discussion_api_key=None,
            scene_path_override=None,
        )

    def test_resume_session_by_id_nonexistent_project_404(self, client, reset_session):
        response = client.post("/api/resume-session", json={
            "project_path": "/nonexistent/path/that/does/not/exist",
            "session_id": 1,
        })
        assert response.status_code == 404

    @patch("web.routes.get_session_detail")
    def test_resume_session_by_id_not_found_404(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.return_value = None

        response = client.post("/api/resume-session", json={
            "project_path": str(tmp_path),
            "session_id": 999,
        })
        assert response.status_code == 404

    @patch("web.routes.get_session_detail")
    def test_resume_session_by_id_completed_session_returns_400(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.return_value = {
            "id": 9,
            "status": "completed",
            "model": "sonnet",
            "discussion_model": None,
        }

        response = client.post("/api/resume-session", json={
            "project_path": str(tmp_path),
            "session_id": 9,
        })
        assert response.status_code == 400
        assert "cannot be resumed" in response.json()["detail"]

    @patch("web.routes._resolve_analysis_and_discussion_keys")
    @patch("web.routes.get_session_detail")
    @patch.object(session_mgr, "load_session_for_viewing", new_callable=AsyncMock)
    def test_view_session_by_id_loads_completed_session_and_returns_summary(
        self,
        mock_view_session,
        mock_get_session_detail,
        mock_resolve_keys,
        client,
        reset_session,
        tmp_path,
    ):
        """POST /api/view-session should load a closed session for viewing/actions."""
        mock_get_session_detail.return_value = {
            "id": 42,
            "status": "completed",
            "model": "sonnet",
            "discussion_model": None,
        }
        mock_resolve_keys.return_value = ("sk-ant-env", None)
        mock_view_session.return_value = {"scene_name": "chapter-01.txt", "total_findings": 5}

        response = client.post("/api/view-session", json={
            "project_path": str(tmp_path),
            "session_id": 42,
        })

        assert response.status_code == 200
        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 42)
        mock_view_session.assert_awaited_once_with(
            str(tmp_path),
            42,
            "sk-ant-env",
            discussion_api_key=None,
            scene_path_override=None,
        )

    def test_view_session_by_id_nonexistent_project_404(self, client, reset_session):
        response = client.post("/api/view-session", json={
            "project_path": "/nonexistent/path/that/does/not/exist",
            "session_id": 1,
        })
        assert response.status_code == 404

    @patch("web.routes.get_session_detail")
    def test_view_session_by_id_not_found_404(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.return_value = None

        response = client.post("/api/view-session", json={
            "project_path": str(tmp_path),
            "session_id": 999,
        })
        assert response.status_code == 404

    @patch("web.routes._resolve_analysis_and_discussion_keys")
    @patch("web.routes.get_session_detail")
    @patch.object(session_mgr, "load_session_for_viewing", new_callable=AsyncMock)
    def test_view_session_returns_409_with_structured_detail_for_missing_scene_path(
        self,
        mock_view_session,
        mock_get_session_detail,
        mock_resolve_keys,
        client,
        reset_session,
        tmp_path,
    ):
        """View-session route should preserve structured path-relink errors for recovery UI."""
        mock_get_session_detail.return_value = {
            "id": 21,
            "status": "abandoned",
            "model": "sonnet",
            "discussion_model": None,
        }
        mock_resolve_keys.return_value = ("sk-ant-explicit", None)
        mock_view_session.side_effect = ResumeScenePathError(
            "Saved scene file was not found.",
            saved_scene_path="D:/old-machine/project/ch01.md",
            attempted_scene_path="D:/old-machine/project/ch01.md",
            project_path=str(tmp_path),
            override_provided=False,
        )

        response = client.post("/api/view-session", json={
            "project_path": str(tmp_path),
            "session_id": 21,
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "scene_path_not_found"
        assert detail["saved_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["attempted_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["project_path"] == str(tmp_path)
        assert detail["override_provided"] is False


class TestStaticFiles:
    """Test that static files are served."""

    def test_css_served(self, client):
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_served(self, client):
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


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
             patch.object(session_mgr, "_load_project_files", return_value=({}, [], [])), \
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

        finding = session_mgr.state.findings[0]
        assert finding.scene_path == str(scene2)
        assert finding.line_start == 1
        assert finding.line_end == 2
        assert finding.location == "L1-L2, second scene issue"


class TestManagementEndpoints:
    """Test session and learning management routes (Phase 2)."""

    # --- Session Management Tests ---

    def test_list_sessions_returns_all_sessions(self, client, temp_project_dir, sample_session_state_with_db):
        """GET /api/sessions should return all sessions for a project."""
        from lit_platform.runtime.session import create_session, complete_session
        from lit_platform.runtime.models import Finding

        # Create a couple sessions
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"])
        ]
        create_session(state)
        complete_session(state)

        state.scene_path = str(temp_project_dir / "scene02.txt")
        create_session(state)

        response = client.get(f"/api/sessions?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert 'sessions' in data
        assert len(data['sessions']) == 2

    def test_list_sessions_empty_project(self, client, temp_project_dir):
        """Should return empty list for new project."""
        response = client.get(f"/api/sessions?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data['sessions'] == []

    def test_list_sessions_nonexistent_project_404(self, client):
        """Should return 404 for nonexistent project."""
        response = client.get("/api/sessions?project_path=/nonexistent/path")
        assert response.status_code == 404

    def test_get_session_detail_returns_full_data(self, client, temp_project_dir, sample_session_state_with_db):
        """GET /api/sessions/{id} should return complete session details."""
        from lit_platform.runtime.session import create_session, complete_session, list_sessions
        from lit_platform.runtime.models import Finding

        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="critical", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"], status="accepted",
                   discussion_turns=[
                       {"role": "user", "content": "This is intentional."},
                       {"role": "assistant", "content": "Understood, adjusting severity."},
                   ]),
            Finding(number=2, severity="major", lens="structure", location="P2",
                   evidence="E2", impact="I2", options=["O2"], flagged_by=["structure"], status="rejected"),
        ]
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        session_id = sessions[0]['id']

        response = client.get(f"/api/sessions/{session_id}?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == session_id
        assert data['status'] == 'completed'
        assert 'findings' in data
        assert len(data['findings']) == 2
        assert data['findings'][0]['discussion_turns'][0]['role'] == 'user'
        assert data['findings'][0]['discussion_turns'][1]['role'] == 'assistant'

    def test_get_session_detail_not_found_404(self, client, temp_project_dir):
        """Should return 404 for nonexistent session."""
        response = client.get(f"/api/sessions/9999?project_path={temp_project_dir}")
        assert response.status_code == 404

    def test_delete_session_returns_deleted_true(self, client, temp_project_dir, sample_session_state_with_db):
        """DELETE /api/sessions/{id} should delete session and return True."""
        from lit_platform.runtime.session import create_session, complete_session, list_sessions
        from lit_platform.runtime.models import Finding

        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"])
        ]
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        session_id = sessions[0]['id']

        response = client.delete(f"/api/sessions/{session_id}?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data['deleted'] is True
        assert data['session_id'] == session_id

        # Verify it's gone
        sessions_after = list_sessions(temp_project_dir)
        assert len(sessions_after) == 0

    def test_delete_session_not_found_404(self, client, temp_project_dir):
        """Should return 404 when deleting nonexistent session."""
        response = client.delete(f"/api/sessions/9999?project_path={temp_project_dir}")
        assert response.status_code == 404

    # --- Learning Management Tests ---

    def test_get_learning_returns_all_categories(self, client, temp_project_dir):
        """GET /api/learning should return all learning categories."""
        from lit_platform.runtime.db import get_connection, LearningStore

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test preference")
            LearningStore.add_blind_spot(conn, "Test blind spot")
            LearningStore.increment_review_count(conn)
        finally:
            conn.close()

        response = client.get(f"/api/learning?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert 'preferences' in data
        assert 'blind_spots' in data
        assert 'resolutions' in data
        assert 'ambiguity_intentional' in data
        assert 'ambiguity_accidental' in data
        assert 'review_count' in data
        assert len(data['preferences']) == 1
        assert len(data['blind_spots']) == 1

    def test_get_learning_nonexistent_project_404(self, client):
        """Should return 404 for nonexistent project."""
        response = client.get("/api/learning?project_path=/nonexistent/path")
        assert response.status_code == 404

    def test_export_learning_creates_file(self, client, temp_project_dir):
        """POST /api/learning/export should create LEARNING.md."""
        from lit_platform.runtime.db import get_connection, LearningStore

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test preference")
        finally:
            conn.close()

        response = client.post("/api/learning/export", json={
            "project_path": str(temp_project_dir)
        })
        assert response.status_code == 200
        data = response.json()
        assert data['exported'] is True
        assert 'path' in data

        # Verify file exists
        learning_file = temp_project_dir / "LEARNING.md"
        assert learning_file.exists()

    def test_export_learning_returns_path(self, client, temp_project_dir):
        """Export should return the file path."""
        response = client.post("/api/learning/export", json={
            "project_path": str(temp_project_dir)
        })
        assert response.status_code == 200
        data = response.json()
        assert str(temp_project_dir / "LEARNING.md") in data['path']

    def test_reset_learning_clears_all_data(self, client, temp_project_dir):
        """DELETE /api/learning should reset all learning data."""
        from lit_platform.runtime.db import get_connection, LearningStore
        from lit_platform.runtime.learning import load_learning

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Pref 1")
            LearningStore.add_preference(conn, "Pref 2")
            LearningStore.add_blind_spot(conn, "Blind spot")
        finally:
            conn.close()

        response = client.delete(f"/api/learning?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data['reset'] is True

        # Verify all data is gone
        learning = load_learning(temp_project_dir)
        assert learning.preferences == []
        assert learning.blind_spots == []

    def test_reset_learning_nonexistent_project_404(self, client):
        """Should return 404 for nonexistent project."""
        response = client.delete("/api/learning?project_path=/nonexistent/path")
        assert response.status_code == 404

    def test_delete_learning_entry_returns_deleted_true(self, client, temp_project_dir):
        """DELETE /api/learning/entries/{id} should delete entry and return True."""
        from lit_platform.runtime.db import get_connection, LearningStore
        from lit_platform.runtime.learning import load_learning

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Preference 1")
            LearningStore.add_preference(conn, "Preference 2")
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        entry_id = learning.preferences[0]['id']

        response = client.delete(f"/api/learning/entries/{entry_id}?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data['deleted'] is True
        assert data['entry_id'] == entry_id

        # Verify one remains
        learning_after = load_learning(temp_project_dir)
        assert len(learning_after.preferences) == 1

    def test_delete_learning_entry_not_found_404(self, client, temp_project_dir):
        """Should return 404 when deleting nonexistent entry."""
        response = client.delete(f"/api/learning/entries/9999?project_path={temp_project_dir}")
        assert response.status_code == 404
