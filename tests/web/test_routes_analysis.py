"""
Tests for analysis, resume, audit, and index routes.
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


class TestAnalyzeEndpoint:
    """Test the analyze endpoint."""

    @pytest.fixture(autouse=True)
    def _repo_preflight_ok(self, monkeypatch):
        monkeypatch.setattr("web.routes_analysis._ensure_repo_preflight_ready", lambda: None)

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

    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_analyze_normalizes_missing_finding_origin(self, mock_start, client, reset_session):
        mock_start.return_value = {
            "complete": False,
            "finding": {
                "number": 1,
                "severity": "major",
                "lens": "structure",
            },
        }

        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene1.txt",
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["finding"]["origin"] == "legacy"

    def test_analyze_requires_scene_path_or_scene_paths(self, client, reset_session):
        response = client.post("/api/analyze", json={
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 400
        assert response.json()["detail"] == "scene_path or scene_paths is required"

    def test_analyze_rejects_deprecated_model_override_fields(self, client, reset_session):
        """Analyze endpoint should reject deprecated explicit model override fields."""
        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "mode": "deep",
            "model": "sonnet",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 400
        assert "Deprecated fields are not supported" in response.json()["detail"]
        assert "model, discussion_model" in response.json()["detail"]

    @patch("web.routes_analysis.get_model_slots", return_value={"frontier": "gpt-4o", "deep": "sonnet", "quick": "haiku"})
    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_analyze_cross_provider_uses_mode_resolved_models_and_separate_keys(self, mock_start, _mock_slots, client, reset_session):
        """Cross-provider analyze should resolve models from mode/slots and pass separate provider keys."""
        mock_start.return_value = {"ok": True}

        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "mode": "deep",
            "api_key": "sk-ant-explicit",
            "discussion_api_key": "sk-openai-explicit",
        })

        assert response.status_code == 200
        mock_start.assert_awaited_once()
        _, kwargs = mock_start.await_args
        assert kwargs["model"] == "sonnet"
        assert kwargs["discussion_model"] == "gpt-4o"
        assert kwargs["discussion_api_key"] == "sk-openai-explicit"
        assert kwargs["depth_mode"] == "deep"

    @patch("web.routes_analysis.get_model_slots", return_value={"frontier": "gpt-4o", "deep": "sonnet", "quick": "haiku"})
    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_analyze_includes_mode_hint_and_tier_cost_summary(self, mock_start, _mock_slots, client, reset_session):
        """Analyze response includes mode estimate hint and tier-level cost summary metadata."""
        mock_start.return_value = {"ok": True, "counts": {"critical": 0, "major": 0, "minor": 0}}

        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "mode": "deep",
            "api_key": "sk-ant-explicit",
            "discussion_api_key": "sk-openai-explicit",
        })

        assert response.status_code == 200
        payload = response.json()

        assert "mode_cost_hint" in payload
        assert "Deep mode" in payload["mode_cost_hint"]

        assert "tier_cost_summary" in payload
        tier = payload["tier_cost_summary"]
        assert tier["mode"] == "deep"
        assert tier["actuals_available"] is False
        assert tier["checker"]["name"] == "sonnet"
        assert tier["frontier"]["name"] == "gpt-4o"
        assert tier["total_cost_usd"] is None

    @patch("web.routes_analysis.get_model_slots", return_value={"frontier": "gpt-4o", "deep": "sonnet", "quick": "haiku"})
    def test_analyze_cross_provider_missing_second_key_returns_400(self, _mock_slots, client, reset_session):
        """Cross-provider analyze should fail early if discussion provider key is missing."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-env"}, clear=True):
            response = client.post("/api/analyze", json={
                "scene_path": "/any/scene.txt",
                "project_path": "/any/project",
                "mode": "deep",
            })

        assert response.status_code == 400
        assert "No API key for provider 'openai'" in response.json()["detail"]

    @patch("web.routes_analysis.get_model_slots", return_value={"frontier": "gpt-4o", "deep": "gpt-4o", "quick": "gpt-4o"})
    def test_analyze_provider_key_mismatch_returns_400(self, _mock_slots, client, reset_session):
        """OpenAI resolved model with Anthropic key should fail with a clear validation error."""
        response = client.post("/api/analyze", json={
            "scene_path": "/any/scene.txt",
            "project_path": "/any/project",
            "mode": "deep",
            "api_key": "sk-ant-mismatch",
        })

        assert response.status_code == 400
        assert "appears to be an Anthropic key" in response.json()["detail"]

    @patch.object(session_mgr, "start_analysis", new_callable=AsyncMock)
    def test_rerun_uses_persisted_scene_paths_and_models(self, mock_start, client, reset_session):
        """Re-run should reuse the persisted scene paths and model choices."""
        mock_start.return_value = {"ok": True}
        session_mgr.state = MagicMock(
            model="sonnet",
            discussion_model=None,
            depth_mode="quick",
            scene_paths=["/any/scene1.txt", "/any/scene2.txt"],
            scene_path="/any/scene1.txt",
        )

        response = client.post("/api/analyze/rerun", json={
            "project_path": "/any/project",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 200
        _, kwargs = mock_start.await_args
        assert kwargs["scene_paths"] == ["/any/scene1.txt", "/any/scene2.txt"]
        assert kwargs["model"] == "sonnet"
        assert kwargs["discussion_model"] is None
        assert kwargs["depth_mode"] == "quick"

    def test_resume_no_session(self, client, reset_session, tmp_path):
        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "test-key",
        })
        assert response.status_code == 404


class TestIndexEndpoint:
    """Test the /api/index endpoint."""

    @pytest.fixture(autouse=True)
    def _repo_preflight_ok(self, monkeypatch):
        monkeypatch.setattr("web.routes_analysis._ensure_repo_preflight_ready", lambda: None)

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("lit_platform.runtime.llm.create_client", return_value=MagicMock())
    @patch("web.routes_analysis.scan_scene_for_index_entries", new_callable=AsyncMock)
    def test_index_uses_resolved_model_id_for_scan(
        self,
        mock_scan,
        _mock_create_client,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        """Index route must pass provider model ID, not short name, to scan service."""
        from lit_platform.runtime.config import resolve_model

        project = tmp_path
        scene = tmp_path / "scene.txt"
        scene.write_text("@@META\nID: 01.01.01\n\nScene content", encoding="utf-8")

        mock_scan.return_value = {
            "scene_id": "01.01.01",
            "cast": {"added": [], "skipped": []},
            "glossary": {"added": [], "skipped": []},
            "threads": {"added": [], "advanced": [], "closed": []},
            "timeline": {"added": [], "skipped": []},
        }

        response = client.post("/api/index", json={
            "scene_path": str(scene),
            "project_path": str(project),
            "model": "haiku",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 200
        _, kwargs = mock_scan.await_args
        assert kwargs["model"] == resolve_model("haiku")["id"]
        assert kwargs["model"] != "haiku"

    @patch("web.routes_analysis.check_active_session")
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

    @patch("web.routes_analysis.check_active_session")
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
            scene_path_overrides=None,
            scene_path_override=None,
        )

    @patch("web.routes_analysis.check_active_session")
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
            scene_path_overrides=None,
        )

    @patch("web.routes_analysis.check_active_session")
    @patch.object(session_mgr, "resume_session", new_callable=AsyncMock)
    def test_resume_passes_scene_path_overrides_map(
        self,
        mock_resume,
        mock_check_active,
        client,
        reset_session,
        tmp_path,
    ):
        """Resume route should pass scene_path_overrides map through to session manager."""
        mock_check_active.return_value = {"exists": False}
        mock_resume.return_value = {"active": True}

        response = client.post("/api/resume", json={
            "project_path": str(tmp_path),
            "api_key": "sk-ant-explicit",
            "scene_path_overrides": {
                "D:/old-machine/project/ch01.md": str(tmp_path / "ch01.md"),
                "D:/old-machine/project/ch02.md": str(tmp_path / "ch02.md"),
            },
        })

        assert response.status_code == 200
        mock_resume.assert_awaited_once_with(
            str(tmp_path),
            "sk-ant-explicit",
            discussion_api_key=None,
            scene_path_override=None,
            scene_path_overrides={
                "D:/old-machine/project/ch01.md": str(tmp_path / "ch01.md"),
                "D:/old-machine/project/ch02.md": str(tmp_path / "ch02.md"),
            },
        )

    @patch("web.routes_analysis.check_active_session")
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
        assert detail["saved_scene_paths"] == ["D:/old-machine/project/ch01.md"]
        assert detail["missing_scene_paths"] == ["D:/old-machine/project/ch01.md"]
        assert detail["project_path"] == str(tmp_path)
        assert detail["override_provided"] is False


class TestAuditEndpoint:
    """Test the /api/audit endpoint."""

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("web.routes_analysis.audit_indexes_deterministic")
    def test_audit_returns_deterministic_payload(
        self,
        mock_deterministic,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        report = MagicMock()
        report.deterministic = [
            SimpleNamespace(
                check_id="placeholder_density",
                severity="warning",
                file="CAST.md",
                location="### Alice",
                message="Contains TODO placeholders",
                related_file=None,
            )
        ]
        report.semantic = []
        report.placeholder_census = {"CAST.md": 2}
        mock_deterministic.return_value = report

        response = client.post("/api/audit", json={
            "project_path": str(tmp_path),
            "deep": False,
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["deterministic"]) == 1
        assert data["deterministic"][0]["check_id"] == "placeholder_density"
        assert data["semantic"] == []
        assert data["placeholder_census"] == {"CAST.md": 2}
        assert data["deep"] is False
        assert data["deep_error"] is None

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("web.routes_analysis.audit_indexes_semantic", new_callable=AsyncMock)
    @patch("web.routes_analysis.audit_indexes_deterministic")
    @patch("lit_platform.runtime.llm.create_client", return_value=MagicMock())
    def test_audit_deep_failure_returns_deterministic_with_deep_error(
        self,
        _mock_create_client,
        mock_deterministic,
        mock_semantic,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        report = MagicMock()
        report.deterministic = [
            SimpleNamespace(
                check_id="timeline_order",
                severity="error",
                file="TIMELINE.md",
                location="**01.02.01**",
                message="Out-of-order timeline",
                related_file=None,
            )
        ]
        report.semantic = []
        report.placeholder_census = {}
        mock_deterministic.return_value = report
        mock_semantic.side_effect = RuntimeError("Deep provider timeout")

        response = client.post("/api/audit", json={
            "project_path": str(tmp_path),
            "deep": True,
            "model": "sonnet",
            "api_key": "sk-ant-explicit",
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["deterministic"]) == 1
        assert data["semantic"] == []
        assert data["deep"] is True
        assert data["model"] == "sonnet"
        assert "Deep provider timeout" in data["deep_error"]

    def test_audit_nonexistent_project_returns_404(self, client):
        response = client.post("/api/audit", json={
            "project_path": "/nonexistent/path/that/does/not/exist",
        })
        assert response.status_code == 404

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("web.routes_analysis.audit_scene", new_callable=AsyncMock)
    def test_scene_audit_quick_success(
        self,
        mock_audit_scene,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        scene_path = tmp_path / "scene.md"
        scene_path.write_text("@@META\nID: 01.01.01\n", encoding="utf-8")
        mock_audit_scene.return_value = {
            "deterministic": [
                Finding(
                    number=1,
                    severity="minor",
                    lens="code",
                    location="line 1",
                    evidence="Missing index crossref",
                    impact="Continuity risk",
                    options=["Add crossref"],
                    origin="code",
                )
            ],
            "semantic": [],
            "deep": False,
            "model": "claude-sonnet-4-20250514",
            "deep_error": None,
        }

        response = client.post(
            "/api/scenes/audit",
            json={
                "project_path": str(tmp_path),
                "scene_path": str(scene_path),
                "deep": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["deterministic"]) == 1
        assert data["deterministic"][0]["origin"] == "code"
        assert data["semantic"] == []
        assert data["deep"] is False
        assert data["deep_error"] is None

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("lit_platform.runtime.llm.create_client", return_value=MagicMock())
    @patch("web.routes_analysis.audit_scene", new_callable=AsyncMock)
    def test_scene_audit_deep_success(
        self,
        mock_audit_scene,
        _mock_create_client,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        scene_path = tmp_path / "scene.md"
        scene_path.write_text("@@META\nID: 01.01.01\n", encoding="utf-8")
        mock_audit_scene.return_value = {
            "deterministic": [],
            "semantic": [
                Finding(
                    number=1,
                    severity="major",
                    lens="continuity",
                    location="paragraph 2",
                    evidence="Contradictory timing",
                    impact="Reader confusion",
                    options=["Clarify chronology"],
                    origin="critic",
                )
            ],
            "deep": True,
            "model": "claude-sonnet-4-20250514",
            "deep_error": None,
        }

        response = client.post(
            "/api/scenes/audit",
            json={
                "project_path": str(tmp_path),
                "scene_path": str(scene_path),
                "deep": True,
                "model": "sonnet",
                "api_key": "sk-ant-explicit",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["semantic"]) == 1
        assert data["semantic"][0]["origin"] == "critic"
        assert data["deep"] is True
        assert data["model"] == "sonnet"
        assert data["deep_error"] is None

    @patch("lit_platform.facade.PlatformFacade.load_legacy_indexes_from_project", return_value={})
    @patch("lit_platform.runtime.llm.create_client", return_value=MagicMock())
    @patch("web.routes_analysis.audit_scene", new_callable=AsyncMock)
    def test_scene_audit_deep_failure_returns_deterministic_with_deep_error(
        self,
        mock_audit_scene,
        _mock_create_client,
        _mock_load_indexes,
        client,
        tmp_path,
    ):
        scene_path = tmp_path / "scene.md"
        scene_path.write_text("@@META\nID: 01.01.01\n", encoding="utf-8")
        mock_audit_scene.return_value = {
            "deterministic": [
                Finding(
                    number=1,
                    severity="minor",
                    lens="code",
                    location="line 4",
                    evidence="Stale reference",
                    impact="Potential mismatch",
                    options=["Update reference"],
                    origin="code",
                )
            ],
            "semantic": [],
            "deep": True,
            "model": "claude-sonnet-4-20250514",
            "deep_error": "Deep provider timeout",
        }

        response = client.post(
            "/api/scenes/audit",
            json={
                "project_path": str(tmp_path),
                "scene_path": str(scene_path),
                "deep": True,
                "model": "sonnet",
                "api_key": "sk-ant-explicit",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["deterministic"]) == 1
        assert data["semantic"] == []
        assert data["deep"] is True
        assert data["model"] == "sonnet"
        assert "Deep provider timeout" in (data["deep_error"] or "")

    def test_scene_audit_nonexistent_project_returns_404(self, client):
        response = client.post(
            "/api/scenes/audit",
            json={
                "project_path": "/nonexistent/path/that/does/not/exist",
                "scene_path": "/nonexistent/path/that/does/not/exist/scene.md",
            },
        )
        assert response.status_code == 404

    def test_scene_audit_missing_scene_returns_404(self, client, tmp_path):
        response = client.post(
            "/api/scenes/audit",
            json={
                "project_path": str(tmp_path),
                "scene_path": str(tmp_path / "missing-scene.md"),
            },
        )
        assert response.status_code == 404

    @patch("web.routes_analysis._resolve_analysis_and_discussion_keys")
    @patch("web.routes_analysis.get_session_detail")
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
            scene_path_overrides=None,
        )

    def test_resume_session_by_id_nonexistent_project_404(self, client, reset_session):
        response = client.post("/api/resume-session", json={
            "project_path": "/nonexistent/path/that/does/not/exist",
            "session_id": 1,
        })
        assert response.status_code == 404

    @patch("web.routes_analysis.get_session_detail")
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

    @patch("web.routes_analysis.get_session_detail")
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

    @patch("web.routes_analysis._resolve_analysis_and_discussion_keys")
    @patch("web.routes_analysis.get_session_detail")
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
        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 42, passive=True)
        mock_view_session.assert_awaited_once_with(
            str(tmp_path),
            42,
            "sk-ant-env",
            discussion_api_key=None,
            scene_path_override=None,
            scene_path_overrides=None,
            passive=True,
            reopen=False,
        )

    @patch("web.routes_analysis._resolve_analysis_and_discussion_keys")
    @patch("web.routes_analysis.get_session_detail")
    @patch.object(session_mgr, "load_session_for_viewing", new_callable=AsyncMock)
    def test_view_session_by_id_reopen_completed_session_uses_explicit_reopen_flow(
        self,
        mock_view_session,
        mock_get_session_detail,
        mock_resolve_keys,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.return_value = {
            "id": 42,
            "status": "completed",
            "model": "sonnet",
            "discussion_model": None,
        }
        mock_resolve_keys.return_value = ("sk-ant-env", None)
        mock_view_session.return_value = {"scene_name": "chapter-01.txt", "total_findings": 5, "read_only": False}

        response = client.post("/api/view-session", json={
            "project_path": str(tmp_path),
            "session_id": 42,
            "reopen": True,
        })

        assert response.status_code == 200
        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 42, passive=True)
        mock_view_session.assert_awaited_once_with(
            str(tmp_path),
            42,
            "sk-ant-env",
            discussion_api_key=None,
            scene_path_override=None,
            scene_path_overrides=None,
            passive=False,
            reopen=True,
        )

    def test_view_session_by_id_nonexistent_project_404(self, client, reset_session):
        response = client.post("/api/view-session", json={
            "project_path": "/nonexistent/path/that/does/not/exist",
            "session_id": 1,
        })
        assert response.status_code == 404

    @patch("web.routes_analysis.get_session_detail")
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

    @patch("web.routes_analysis._resolve_analysis_and_discussion_keys")
    @patch("web.routes_analysis.get_session_detail")
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

        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 21, passive=True)
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "scene_path_not_found"
        assert detail["saved_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["attempted_scene_path"] == "D:/old-machine/project/ch01.md"
        assert detail["saved_scene_paths"] == ["D:/old-machine/project/ch01.md"]
        assert detail["missing_scene_paths"] == ["D:/old-machine/project/ch01.md"]
        assert detail["project_path"] == str(tmp_path)
        assert detail["override_provided"] is False


