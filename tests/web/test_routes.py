"""
Tests for the lit-critic Web UI.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from fastapi.testclient import TestClient

from web.app import app
from web.routes import session_mgr
from server.models import Finding, SessionState, LearningData


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
    session_mgr.skip_minor = False
    session_mgr.analysis_progress = None
    yield
    session_mgr.state = None
    session_mgr.results = None
    session_mgr.current_index = 0
    session_mgr.skip_minor = False
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

    def test_save_session_no_active(self, client, reset_session):
        response = client.post("/api/session/save")
        assert response.status_code == 404

    def test_save_learning_no_active(self, client, reset_session):
        response = client.post("/api/learning/save")
        assert response.status_code == 404

    def test_skip_minor_no_session(self, client, reset_session):
        response = client.post("/api/finding/skip-minor")
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

    @patch("web.session_manager.session_exists")
    @patch("web.session_manager.load_session")
    def test_check_existing_session(self, mock_load, mock_exists, client, reset_session, tmp_path):
        mock_exists.return_value = True
        mock_load.return_value = {
            "scene_path": str(tmp_path / "scene.txt"),
            "saved_at": "2025-01-01T12:00:00",
            "current_index": 3,
            "findings": [1, 2, 3, 4, 5],
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
            learning=learning,
            findings=findings,
        )
        session_mgr.current_index = 0
        session_mgr.skip_minor = False

    def test_get_session_active(self, client, active_session):
        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["total_findings"] == 3

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

    def test_skip_minor(self, client, active_session):
        response = client.post("/api/finding/skip-minor")
        assert response.status_code == 200
        data = response.json()
        # Should skip finding #3 (minor) and show #2 (major) next
        assert data["complete"] is False
        assert data["finding"]["number"] == 2

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
        """Goto a withdrawn finding returns complete (not available)."""
        session_mgr.state.findings[1].status = 'withdrawn'
        response = client.post("/api/finding/goto", json={"index": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is True

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
        assert data["complete"] is True

    @patch("web.session_manager.handle_discussion")
    def test_discuss_finding(self, mock_discuss, client, active_session):
        mock_discuss.return_value = ("Good point, I concede.", "conceded")

        response = client.post("/api/finding/discuss", json={"message": "This is intentional"})
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Good point, I concede."
        assert data["status"] == "conceded"
        assert data["finding_status"] == "rejected"

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
        """Config reports no key when env var is unset."""
        import os
        env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            response = client.get("/api/config")
            assert response.status_code == 200
            assert response.json()["api_key_configured"] is False
        finally:
            if env_backup:
                os.environ["ANTHROPIC_API_KEY"] = env_backup

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


class TestAnalyzeEndpoint:
    """Test the analyze endpoint."""

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

    def test_resume_no_session(self, client, reset_session, tmp_path):
        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "test-key",
        })
        assert response.status_code == 404


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
