"""
Tests for management routes (sessions, scenes, indexes, knowledge, analytics, learning).
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

    def test_list_sessions_empty_project_does_not_create_db(self, client, temp_project_dir):
        """Passive startup session listing should not create lit-critic.db."""
        from lit_platform.runtime.config import DB_FILE

        db_path = temp_project_dir / DB_FILE
        assert db_path.exists() is False

        response = client.get(f"/api/sessions?project_path={temp_project_dir}")

        assert response.status_code == 200
        assert response.json()['sessions'] == []
        assert db_path.exists() is False

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

    @patch("web.routes_management.get_session_detail")
    def test_get_session_detail_route_uses_passive_detail_for_closed_session(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.return_value = {
            "id": 7,
            "status": "completed",
            "findings": [],
        }

        response = client.get(f"/api/sessions/7?project_path={tmp_path}")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        mock_get_session_detail.assert_called_once_with(Path(str(tmp_path)), 7, passive=True)

    @patch("web.routes_management.get_session_detail")
    def test_get_session_detail_route_falls_back_to_mutable_read_for_active_session(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.side_effect = [
            {"id": 8, "status": "active", "findings": []},
            {"id": 8, "status": "active", "findings": [], "accepted_count": 1},
        ]

        response = client.get(f"/api/sessions/8?project_path={tmp_path}")

        assert response.status_code == 200
        assert response.json()["status"] == "active"
        assert mock_get_session_detail.call_args_list == [
            ((Path(str(tmp_path)), 8), {"passive": True}),
            ((Path(str(tmp_path)), 8), {}),
        ]

    @patch("web.routes_management.get_session_detail")
    def test_get_session_detail_route_preserves_passive_depth_mode_when_mutable_differs(
        self,
        mock_get_session_detail,
        client,
        reset_session,
        tmp_path,
    ):
        mock_get_session_detail.side_effect = [
            {"id": 9, "status": "active", "depth_mode": "preflight", "findings": []},
            {"id": 9, "status": "active", "depth_mode": "deep", "findings": [], "accepted_count": 1},
        ]

        response = client.get(f"/api/sessions/9?project_path={tmp_path}")

        assert response.status_code == 200
        data = response.json()
        assert data["accepted_count"] == 1
        assert data["depth_mode"] == "preflight"
        assert mock_get_session_detail.call_args_list == [
            ((Path(str(tmp_path)), 9), {"passive": True}),
            ((Path(str(tmp_path)), 9), {}),
        ]

    def test_mutating_route_rejects_read_only_loaded_session(self, client, reset_session):
        session_mgr.state = SimpleNamespace(findings=[SimpleNamespace()])
        session_mgr.read_only_view = True

        response = client.post("/api/finding/accept")

        assert response.status_code == 409
        assert "read-only mode" in response.json()["detail"]

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

    @patch("web.routes_management.list_scene_projections")
    def test_list_scenes_returns_projection_rows(
        self,
        mock_list_scene_projections,
        client,
        temp_project_dir,
    ):
        """GET /api/scenes should return projected scene rows."""
        mock_list_scene_projections.return_value = [
            {
                "scene_path": "text/chapter-01.txt",
                "scene_id": "scene-01",
                "file_hash": "abc123",
                "meta_json": {"id": "scene-01"},
            }
        ]

        response = client.get(f"/api/scenes?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data["scenes"] == mock_list_scene_projections.return_value
        mock_list_scene_projections.assert_called_once_with(Path(str(temp_project_dir)))

    @patch("web.routes_management.refresh_project_knowledge")
    def test_refresh_scenes_returns_refresh_summary(
        self,
        mock_refresh_project_knowledge,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/refresh should report totals and updates."""
        mock_refresh_project_knowledge.return_value = {
            "scenes": [{"scene_path": "text/chapter-01.txt", "updated": True}],
            "indexes": [{"index_name": "CANON.md", "updated": False}],
            "scene_total": 1,
            "scene_updated": 1,
            "index_total": 1,
            "index_updated": 0,
        }

        response = client.post(
            "/api/scenes/refresh",
            json={"project_path": str(temp_project_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deprecated"] is True
        assert data["replacement"] == "/api/knowledge/refresh"
        assert data["scene_total"] == 1
        assert data["index_total"] == 1
        assert data["scenes"] == mock_refresh_project_knowledge.return_value["scenes"]
        assert mock_refresh_project_knowledge.call_count == 1
        assert mock_refresh_project_knowledge.call_args[0][0] == Path(str(temp_project_dir))

    @patch("web.routes_management.ExtractionStore.lock_scene")
    def test_lock_scene_returns_locked_true(
        self,
        mock_lock_scene,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/lock should lock extraction for one scene."""
        response = client.post(
            "/api/scenes/lock",
            json={
                "project_path": str(temp_project_dir),
                "scene_filename": "text/chapter-01.txt",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "locked": True,
            "scene_filename": "text/chapter-01.txt",
        }
        mock_lock_scene.assert_called_once()

    @patch("web.routes_management.ExtractionStore.unlock_scene")
    def test_unlock_scene_returns_unlocked_true(
        self,
        mock_unlock_scene,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/unlock should unlock extraction for one scene."""
        response = client.post(
            "/api/scenes/unlock",
            json={
                "project_path": str(temp_project_dir),
                "scene_filename": "text/chapter-01.txt",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "unlocked": True,
            "scene_filename": "text/chapter-01.txt",
        }
        mock_unlock_scene.assert_called_once()

    @patch("web.routes_management.rename_scene")
    def test_rename_scene_returns_renamed_payload(
        self,
        mock_rename_scene,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/rename should return rename summary payload."""
        mock_rename_scene.return_value = {
            "old_scene": "text/chapter-01.txt",
            "new_scene": "text/chapter-01-renamed.txt",
            "updated_scene_files": ["text/chapter-02.txt"],
            "updated_scene_projection_row": 1,
            "updated_scene_projection_meta_rows": 1,
            "updated_extracted_scene_metadata_row": 1,
            "updated_extracted_thread_events_rows": 0,
            "updated_extracted_timeline_row": 0,
            "updated_session_rows": 1,
        }

        response = client.post(
            "/api/scenes/rename",
            json={
                "project_path": str(temp_project_dir),
                "old_filename": "text/chapter-01.txt",
                "new_filename": "text/chapter-01-renamed.txt",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["renamed"] is True
        assert payload["old_scene"] == "text/chapter-01.txt"
        assert payload["new_scene"] == "text/chapter-01-renamed.txt"
        mock_rename_scene.assert_called_once()

    @patch("web.routes_management.rename_scene")
    def test_rename_scene_missing_source_returns_404(
        self,
        mock_rename_scene,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/rename should map FileNotFoundError to 404."""
        mock_rename_scene.side_effect = FileNotFoundError("Scene file not found")

        response = client.post(
            "/api/scenes/rename",
            json={
                "project_path": str(temp_project_dir),
                "old_filename": "text/missing.txt",
                "new_filename": "text/chapter-01-renamed.txt",
            },
        )

        assert response.status_code == 404
        assert "Scene file not found" in response.json()["detail"]

    @patch("web.routes_management.rename_scene")
    def test_rename_scene_conflict_returns_409(
        self,
        mock_rename_scene,
        client,
        temp_project_dir,
    ):
        """POST /api/scenes/rename should map FileExistsError to 409."""
        mock_rename_scene.side_effect = FileExistsError("Target scene file already exists")

        response = client.post(
            "/api/scenes/rename",
            json={
                "project_path": str(temp_project_dir),
                "old_filename": "text/chapter-01.txt",
                "new_filename": "text/chapter-02.txt",
            },
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @patch("web.routes_management.compute_file_hash")
    @patch("web.routes_management.list_scene_projections")
    def test_scene_status_reports_projection_freshness(
        self,
        mock_list_scene_projections,
        mock_compute_file_hash,
        client,
        temp_project_dir,
    ):
        """GET /api/scenes/{scene_path}/status should report stale/projected flags."""
        scene_file = temp_project_dir / "text" / "chapter-01.txt"
        scene_file.parent.mkdir(parents=True, exist_ok=True)
        scene_file.write_text("scene content", encoding="utf-8")

        mock_compute_file_hash.return_value = "hash-1"
        mock_list_scene_projections.return_value = [
            {"scene_path": "text/chapter-01.txt", "file_hash": "hash-1"}
        ]

        response = client.get(
            f"/api/scenes/text/chapter-01.txt/status?project_path={temp_project_dir}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "scene_path": "text/chapter-01.txt",
            "stale": False,
            "projected": True,
            "file_hash": "hash-1",
            "stored_hash": "hash-1",
        }
        mock_compute_file_hash.assert_called_once_with(scene_file)
        mock_list_scene_projections.assert_called_once_with(Path(str(temp_project_dir)))

    def test_scene_status_nonexistent_scene_404(self, client, temp_project_dir):
        """Scene status endpoint returns 404 when scene file is missing."""
        response = client.get(
            f"/api/scenes/text/missing.txt/status?project_path={temp_project_dir}"
        )
        assert response.status_code == 404

    @patch("web.routes_management.list_index_projections")
    def test_list_indexes_returns_projection_rows(
        self,
        mock_list_index_projections,
        client,
        temp_project_dir,
    ):
        """GET /api/indexes should return projected index rows."""
        mock_list_index_projections.return_value = [
            {
                "index_name": "CAST.md",
                "file_hash": "hash-cast",
                "entries_json": [{"entry": "Aria Vale"}],
            }
        ]

        response = client.get(f"/api/indexes?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data["indexes"] == mock_list_index_projections.return_value
        mock_list_index_projections.assert_called_once_with(Path(str(temp_project_dir)))

    @patch("web.routes_management.refresh_project_knowledge")
    def test_refresh_indexes_returns_refresh_summary(
        self,
        mock_refresh_project_knowledge,
        client,
        temp_project_dir,
    ):
        """POST /api/indexes/refresh should report totals and updates."""
        mock_refresh_project_knowledge.return_value = {
            "scenes": [{"scene_path": "text/chapter-01.txt", "updated": True}],
            "indexes": [{"index_name": "CANON.md", "updated": True}],
            "scene_total": 1,
            "scene_updated": 1,
            "index_total": 1,
            "index_updated": 1,
        }

        response = client.post(
            "/api/indexes/refresh",
            json={"project_path": str(temp_project_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deprecated"] is True
        assert data["replacement"] == "/api/knowledge/refresh"
        assert data["index_total"] == 1
        assert data["indexes"] == mock_refresh_project_knowledge.return_value["indexes"]
        assert mock_refresh_project_knowledge.call_count == 1
        assert mock_refresh_project_knowledge.call_args[0][0] == Path(str(temp_project_dir))

    @patch("web.routes_management.get_stale_indexes")
    @patch("web.routes_management.list_index_projections")
    def test_indexes_status_returns_stale_index_summary(
        self,
        mock_list_index_projections,
        mock_get_stale_indexes,
        client,
        temp_project_dir,
    ):
        """GET /api/indexes/status returns stale keys and projection count."""
        mock_get_stale_indexes.return_value = ["CAST.md"]
        mock_list_index_projections.return_value = [
            {"index_name": "CAST.md"},
            {"index_name": "GLOSSARY.md"},
        ]

        response = client.get(f"/api/indexes/status?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "stale_indexes": ["CAST.md"],
            "stale_count": 1,
            "projected_count": 2,
            "deprecated": True,
            "replacement": "/api/knowledge/refresh",
        }
        mock_get_stale_indexes.assert_called_once_with(Path(str(temp_project_dir)))
        mock_list_index_projections.assert_called_once_with(Path(str(temp_project_dir)))

    @patch("web.routes_management.refresh_project_knowledge")
    def test_project_refresh_returns_orchestrator_payload(
        self,
        mock_refresh_project_knowledge,
        client,
        temp_project_dir,
    ):
        """POST /api/project/refresh proxies refresh payload."""
        mock_refresh_project_knowledge.return_value = {
            "scenes": [{"scene_path": "text/chapter-01.txt", "updated": True}],
            "indexes": [{"index_name": "CAST.md", "updated": True}],
            "scene_total": 1,
            "scene_updated": 1,
            "index_total": 1,
            "index_updated": 1,
        }

        response = client.post(
            "/api/project/refresh",
            json={"project_path": str(temp_project_dir)},
        )
        assert response.status_code == 200
        assert response.json() == mock_refresh_project_knowledge.return_value
        mock_refresh_project_knowledge.assert_called_once_with(Path(str(temp_project_dir)))

    @patch("web.routes_management.refresh_project_knowledge")
    def test_knowledge_refresh_returns_orchestrator_payload(
        self,
        mock_refresh_project_knowledge,
        client,
        temp_project_dir,
    ):
        """POST /api/knowledge/refresh proxies refresh payload."""
        mock_refresh_project_knowledge.return_value = {
            "scenes": [{"scene_path": "text/chapter-01.txt", "updated": True}],
            "indexes": [{"index_name": "CANON.md", "updated": True}],
            "scene_total": 1,
            "scene_updated": 1,
            "index_total": 1,
            "index_updated": 1,
            "chain_warnings": [],
            "extraction": {"scenes_processed": 1, "failed_scenes": []},
        }

        response = client.post(
            "/api/knowledge/refresh",
            json={"project_path": str(temp_project_dir)},
        )

        assert response.status_code == 200
        assert response.json() == mock_refresh_project_knowledge.return_value
        mock_refresh_project_knowledge.assert_called_once_with(Path(str(temp_project_dir)))

    @patch("web.routes_management.get_passive_connection")
    @patch("web.routes_management.get_knowledge_review")
    def test_get_knowledge_review_returns_category_payload(
        self,
        mock_get_knowledge_review,
        mock_get_passive_connection,
        client,
        temp_project_dir,
    ):
        """GET /api/knowledge/review returns extracted entities + overrides."""
        mock_get_passive_connection.return_value = MagicMock()
        mock_get_knowledge_review.return_value = {
            "category": "characters",
            "entity_key_field": "name",
            "items": [{"name": "Aria Vale"}],
            "overrides": [{"entity_key": "Aria Vale", "field_name": "traits", "value": "focused"}],
        }

        response = client.get(
            "/api/knowledge/review"
            f"?category=characters&project_path={temp_project_dir}"
        )

        assert response.status_code == 200
        assert response.json() == mock_get_knowledge_review.return_value
        mock_get_knowledge_review.assert_called_once()
        _, category_arg = mock_get_knowledge_review.call_args[0]
        assert category_arg == "characters"

    @patch("web.routes_management.submit_override")
    def test_submit_knowledge_override_returns_updated(
        self,
        mock_submit_override,
        client,
        temp_project_dir,
    ):
        """POST /api/knowledge/override stores one override field."""
        response = client.post(
            "/api/knowledge/override",
            json={
                "project_path": str(temp_project_dir),
                "category": "characters",
                "entity_key": "Aria Vale",
                "field_name": "traits",
                "value": "focused",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "updated": True,
            "category": "characters",
            "entity_key": "Aria Vale",
            "field_name": "traits",
        }
        mock_submit_override.assert_called_once()

    @patch("web.routes_management.delete_knowledge_override")
    def test_delete_knowledge_override_returns_deleted(
        self,
        mock_delete_override,
        client,
        temp_project_dir,
    ):
        """DELETE /api/knowledge/override deletes one override field."""
        mock_delete_override.return_value = True

        response = client.request(
            "DELETE",
            "/api/knowledge/override",
            json={
                "project_path": str(temp_project_dir),
                "category": "characters",
                "entity_key": "Aria Vale",
                "field_name": "traits",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "deleted": True,
            "category": "characters",
            "entity_key": "Aria Vale",
            "field_name": "traits",
        }
        mock_delete_override.assert_called_once()

    @patch("web.routes_management.export_knowledge_markdown")
    def test_export_knowledge_returns_markdown(
        self,
        mock_export_knowledge,
        client,
        temp_project_dir,
    ):
        """POST /api/knowledge/export returns markdown payload."""
        mock_export_knowledge.return_value = "# Knowledge Export\n\n## Characters"

        response = client.post(
            "/api/knowledge/export",
            json={"project_path": str(temp_project_dir)},
        )

        assert response.status_code == 200
        assert response.json() == {"markdown": "# Knowledge Export\n\n## Characters"}
        mock_export_knowledge.assert_called_once()

    @patch("web.routes_management.get_project_knowledge_status")
    def test_project_status_returns_knowledge_summary(
        self,
        mock_get_project_knowledge_status,
        client,
        temp_project_dir,
    ):
        """GET /api/project/status proxies knowledge freshness payload."""
        mock_get_project_knowledge_status.return_value = {
            "scenes": {"total": 2, "stale": 1, "fresh": 1, "last_refreshed_at": None},
            "indexes": {"total": 3, "stale": 0, "fresh": 3, "last_refreshed_at": None},
            "stale_total": 1,
            "fresh_total": 4,
        }

        response = client.get(f"/api/project/status?project_path={temp_project_dir}")
        assert response.status_code == 200
        assert response.json() == mock_get_project_knowledge_status.return_value
        mock_get_project_knowledge_status.assert_called_once_with(Path(str(temp_project_dir)))

    def test_project_status_nonexistent_project_404(self, client):
        """Project status endpoint should return 404 for missing project directory."""
        response = client.get("/api/project/status?project_path=/nonexistent/path")
        assert response.status_code == 404

    @patch("web.routes_management.get_rejection_pattern_analytics")
    def test_rejection_pattern_analytics_returns_versioned_payload(
        self,
        mock_get_analytics,
        client,
        temp_project_dir,
    ):
        """GET /api/analytics/rejection-patterns returns stable, explicit schema."""
        mock_get_analytics.return_value = [
            {"lens": "prose", "severity": "major", "rejection_count": 3},
            {"lens": "structure", "severity": "critical", "rejection_count": 1},
        ]

        response = client.get(f"/api/analytics/rejection-patterns?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()

        assert data["analytics_version"] == "v1"
        assert data["filters"] == {
            "limit": 50,
            "start_date": None,
            "end_date": None,
        }
        assert data["rows"] == mock_get_analytics.return_value

        mock_get_analytics.assert_called_once_with(
            Path(str(temp_project_dir)),
            limit=50,
            start_date=None,
            end_date=None,
        )

    @patch("web.routes_management.get_rejection_pattern_analytics")
    def test_rejection_pattern_analytics_forwards_filter_params(
        self,
        mock_get_analytics,
        client,
        temp_project_dir,
    ):
        """Endpoint forwards query filters to service call."""
        mock_get_analytics.return_value = []

        response = client.get(
            "/api/analytics/rejection-patterns"
            f"?project_path={temp_project_dir}"
            "&limit=25"
            "&start_date=2026-01-01"
            "&end_date=2026-01-31"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filters"] == {
            "limit": 25,
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }

        mock_get_analytics.assert_called_once_with(
            Path(str(temp_project_dir)),
            limit=25,
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    def test_rejection_pattern_analytics_rejects_invalid_date_range(self, client, temp_project_dir):
        """start_date after end_date should fail fast with 400."""
        response = client.get(
            "/api/analytics/rejection-patterns"
            f"?project_path={temp_project_dir}"
            "&start_date=2026-02-01"
            "&end_date=2026-01-01"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "start_date must be less than or equal to end_date"

    def test_rejection_pattern_analytics_nonexistent_project_404(self, client):
        """Endpoint should return 404 when project directory does not exist."""
        response = client.get("/api/analytics/rejection-patterns?project_path=/nonexistent/path")
        assert response.status_code == 404

    @patch("web.routes_management.get_acceptance_rate_trend")
    def test_acceptance_rate_trend_returns_versioned_payload(
        self,
        mock_get_trend,
        client,
        temp_project_dir,
    ):
        """GET /api/analytics/acceptance-rate-trend returns stable, explicit schema."""
        mock_get_trend.return_value = [
            {
                "bucket_start": "2026-01-01",
                "accepted_count": 3,
                "rejected_count": 1,
                "sample_size": 4,
                "acceptance_rate": 0.75,
            },
            {
                "bucket_start": "2026-01-02",
                "accepted_count": 1,
                "rejected_count": 1,
                "sample_size": 2,
                "acceptance_rate": 0.5,
            },
        ]

        response = client.get(f"/api/analytics/acceptance-rate-trend?project_path={temp_project_dir}")
        assert response.status_code == 200
        data = response.json()

        assert data["analytics_version"] == "v1"
        assert data["filters"] == {
            "bucket": "daily",
            "window": 30,
            "start_date": None,
            "end_date": None,
        }
        assert data["summary"] == {
            "sample_size": 6,
            "points": 2,
        }
        assert data["rows"] == mock_get_trend.return_value

        mock_get_trend.assert_called_once_with(
            Path(str(temp_project_dir)),
            bucket="daily",
            window=30,
            start_date=None,
            end_date=None,
        )

    @patch("web.routes_management.get_acceptance_rate_trend")
    def test_acceptance_rate_trend_forwards_filter_params(
        self,
        mock_get_trend,
        client,
        temp_project_dir,
    ):
        """Endpoint forwards trend filters to service call."""
        mock_get_trend.return_value = []

        response = client.get(
            "/api/analytics/acceptance-rate-trend"
            f"?project_path={temp_project_dir}"
            "&bucket=weekly"
            "&window=12"
            "&start_date=2026-01-01"
            "&end_date=2026-03-01"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["filters"] == {
            "bucket": "weekly",
            "window": 12,
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
        }
        assert data["summary"] == {
            "sample_size": 0,
            "points": 0,
        }
        assert data["rows"] == []

        mock_get_trend.assert_called_once_with(
            Path(str(temp_project_dir)),
            bucket="weekly",
            window=12,
            start_date="2026-01-01",
            end_date="2026-03-01",
        )

    def test_acceptance_rate_trend_rejects_invalid_date_range(self, client, temp_project_dir):
        """start_date after end_date should fail fast with 400."""
        response = client.get(
            "/api/analytics/acceptance-rate-trend"
            f"?project_path={temp_project_dir}"
            "&start_date=2026-03-01"
            "&end_date=2026-01-01"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "start_date must be less than or equal to end_date"

    @patch("web.routes_management.get_acceptance_rate_trend")
    def test_acceptance_rate_trend_rejects_unsupported_bucket(
        self,
        mock_get_trend,
        client,
        temp_project_dir,
    ):
        """Unsupported bucket values should return HTTP 400."""
        mock_get_trend.side_effect = ValueError("Unsupported bucket: monthly")

        response = client.get(
            "/api/analytics/acceptance-rate-trend"
            f"?project_path={temp_project_dir}"
            "&bucket=monthly"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported bucket: monthly"

    def test_acceptance_rate_trend_nonexistent_project_404(self, client):
        """Endpoint should return 404 when project directory does not exist."""
        response = client.get("/api/analytics/acceptance-rate-trend?project_path=/nonexistent/path")
        assert response.status_code == 404

    @patch("web.routes_management.get_scene_finding_history")
    def test_scene_finding_history_returns_versioned_payload(
        self,
        mock_get_history,
        client,
        temp_project_dir,
    ):
        """GET /api/analytics/scene-finding-history returns stable, explicit schema."""
        mock_get_history.return_value = [
            {"id": 11, "scene_path": "scenes/ch1.md", "session_id": 3},
            {"id": 7, "scene_path": "scenes/ch1.md", "session_id": 2},
        ]

        response = client.get(
            "/api/analytics/scene-finding-history"
            f"?project_path={temp_project_dir}"
            "&scene_id=scenes/ch1.md"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["analytics_version"] == "v1"
        assert data["filters"] == {
            "scene_id": "scenes/ch1.md",
            "limit": 50,
            "offset": 0,
        }
        assert data["rows"] == mock_get_history.return_value

        mock_get_history.assert_called_once_with(
            Path(str(temp_project_dir)),
            scene_id="scenes/ch1.md",
            limit=50,
            offset=0,
        )

    @patch("web.routes_management.get_scene_finding_history")
    def test_scene_finding_history_forwards_pagination_filters(
        self,
        mock_get_history,
        client,
        temp_project_dir,
    ):
        """Endpoint forwards scene and pagination controls to the service."""
        mock_get_history.return_value = []

        response = client.get(
            "/api/analytics/scene-finding-history"
            f"?project_path={temp_project_dir}"
            "&scene_id=scenes/ch2.md"
            "&limit=25"
            "&offset=10"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["filters"] == {
            "scene_id": "scenes/ch2.md",
            "limit": 25,
            "offset": 10,
        }
        assert data["rows"] == []

        mock_get_history.assert_called_once_with(
            Path(str(temp_project_dir)),
            scene_id="scenes/ch2.md",
            limit=25,
            offset=10,
        )

    def test_scene_finding_history_requires_scene_id(self, client, temp_project_dir):
        """scene_id is required for scene-history analytics endpoint."""
        response = client.get(f"/api/analytics/scene-finding-history?project_path={temp_project_dir}")
        assert response.status_code == 422

    def test_scene_finding_history_nonexistent_project_404(self, client):
        """Endpoint should return 404 when project directory does not exist."""
        response = client.get(
            "/api/analytics/scene-finding-history"
            "?project_path=/nonexistent/path"
            "&scene_id=scenes/ch1.md"
        )
        assert response.status_code == 404

    @patch("web.routes_management.get_index_coverage_gaps")
    def test_index_coverage_gaps_returns_versioned_payload(
        self,
        mock_get_coverage,
        client,
        temp_project_dir,
    ):
        """GET /api/analytics/index-coverage-gaps returns stable, explicit schema."""
        mock_get_coverage.return_value = {
            "filters": {
                "session_start_id": 2,
                "session_end_id": 8,
                "scopes": ["cast"],
            },
            "summary": {
                "reviewed_scene_count": 3,
                "indexed_entry_count": 10,
                "gap_count": 2,
            },
            "reviewed_scene_paths": ["scenes/ch1.md", "scenes/ch2.md", "scenes/ch3.md"],
            "missing_scene_paths": ["scenes/ch3.md"],
            "rows": [
                {
                    "scope": "cast",
                    "entry": "Aria Vale",
                    "source_file": "CAST.md",
                    "source_section": "Primary Cast",
                    "source_line": 14,
                    "referenced_scene_paths": [],
                }
            ],
        }

        response = client.get(
            "/api/analytics/index-coverage-gaps"
            f"?project_path={temp_project_dir}"
            "&session_start_id=2"
            "&session_end_id=8"
            "&scopes=cast"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["analytics_version"] == "v1"
        assert data["filters"] == {
            "session_start_id": 2,
            "session_end_id": 8,
            "scopes": ["cast"],
        }
        assert data["summary"] == {
            "reviewed_scene_count": 3,
            "indexed_entry_count": 10,
            "gap_count": 2,
        }
        assert data["reviewed_scene_paths"] == ["scenes/ch1.md", "scenes/ch2.md", "scenes/ch3.md"]
        assert data["missing_scene_paths"] == ["scenes/ch3.md"]
        assert data["rows"] == mock_get_coverage.return_value["rows"]

        mock_get_coverage.assert_called_once_with(
            Path(str(temp_project_dir)),
            session_start_id=2,
            session_end_id=8,
            scopes=["cast"],
        )

    @patch("web.routes_management.get_index_coverage_gaps")
    def test_index_coverage_gaps_forwards_optional_filters(
        self,
        mock_get_coverage,
        client,
        temp_project_dir,
    ):
        """Endpoint forwards optional range and repeated scope filters."""
        mock_get_coverage.return_value = {
            "filters": {
                "session_start_id": None,
                "session_end_id": None,
                "scopes": ["cast", "glossary"],
            },
            "summary": {
                "reviewed_scene_count": 0,
                "indexed_entry_count": 0,
                "gap_count": 0,
            },
            "reviewed_scene_paths": [],
            "missing_scene_paths": [],
            "rows": [],
        }

        response = client.get(
            "/api/analytics/index-coverage-gaps"
            f"?project_path={temp_project_dir}"
            "&scopes=cast"
            "&scopes=glossary"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filters"] == {
            "session_start_id": None,
            "session_end_id": None,
            "scopes": ["cast", "glossary"],
        }
        assert data["summary"]["gap_count"] == 0
        assert data["rows"] == []

        mock_get_coverage.assert_called_once_with(
            Path(str(temp_project_dir)),
            session_start_id=None,
            session_end_id=None,
            scopes=["cast", "glossary"],
        )

    def test_index_coverage_gaps_rejects_invalid_session_range(self, client, temp_project_dir):
        """session_start_id greater than session_end_id should fail fast with 400."""
        response = client.get(
            "/api/analytics/index-coverage-gaps"
            f"?project_path={temp_project_dir}"
            "&session_start_id=10"
            "&session_end_id=2"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "session_start_id must be less than or equal to session_end_id"

    @patch("web.routes_management.get_index_coverage_gaps")
    def test_index_coverage_gaps_rejects_unsupported_scope(
        self,
        mock_get_coverage,
        client,
        temp_project_dir,
    ):
        """Unsupported scope values should return HTTP 400."""
        mock_get_coverage.side_effect = ValueError("Unsupported index coverage scope: timeline")

        response = client.get(
            "/api/analytics/index-coverage-gaps"
            f"?project_path={temp_project_dir}"
            "&scopes=timeline"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported index coverage scope: timeline"

    def test_index_coverage_gaps_nonexistent_project_404(self, client):
        """Endpoint should return 404 when project directory does not exist."""
        response = client.get("/api/analytics/index-coverage-gaps?project_path=/nonexistent/path")
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

    def test_get_learning_empty_project_does_not_create_db(self, client, temp_project_dir):
        """Passive startup learning load should not create lit-critic.db."""
        from lit_platform.runtime.config import DB_FILE

        db_path = temp_project_dir / DB_FILE
        assert db_path.exists() is False

        response = client.get(f"/api/learning?project_path={temp_project_dir}")

        assert response.status_code == 200
        data = response.json()
        assert data['project_name'] == 'Unknown'
        assert data['review_count'] == 0
        assert data['preferences'] == []
        assert db_path.exists() is False

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
