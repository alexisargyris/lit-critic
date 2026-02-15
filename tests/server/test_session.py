"""
Tests for the server.session module (SQLite-backed).
"""

import pytest
from pathlib import Path
from server.session import (
    compute_scene_hash,
    create_session,
    check_active_session,
    load_active_session,
    complete_session,
    abandon_session,
    abandon_active_session,
    complete_active_session,
    delete_session_by_id,
    list_sessions,
    get_session_detail,
    validate_session,
    persist_finding,
    persist_session_index,
    persist_session_learning,
    all_findings_considered,
    detect_and_apply_scene_changes,
)
from server.db import SessionStore, FindingStore
from server.models import Finding


class TestComputeSceneHash:
    def test_returns_string(self):
        assert isinstance(compute_scene_hash("test"), str)

    def test_consistent(self):
        h1 = compute_scene_hash("content")
        h2 = compute_scene_hash("content")
        assert h1 == h2

    def test_different_content(self):
        assert compute_scene_hash("a") != compute_scene_hash("b")

    def test_length(self):
        assert len(compute_scene_hash("x")) == 16


class TestCreateSession:
    def test_creates_session_in_db(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                    evidence="Test", impact="Impact", options=["Fix"]),
        ]
        state.glossary_issues = ["Issue 1"]

        sid = create_session(state, state.glossary_issues)
        assert sid > 0
        assert state.session_id == sid
        assert state.db_conn is not None

        # Verify finding was persisted
        findings = FindingStore.load_all(state.db_conn, sid)
        assert len(findings) == 1
        assert findings[0]["severity"] == "major"

    def test_populates_session_id(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)
        assert state.session_id is not None


class TestCheckActiveSession:
    def test_no_active(self, temp_project_dir):
        result = check_active_session(temp_project_dir)
        assert result["exists"] is False

    def test_with_active(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1")]
        create_session(state)

        result = check_active_session(state.project_path)
        assert result["exists"] is True
        assert result["total_findings"] == 1


class TestLoadActiveSession:
    def test_no_active(self, temp_project_dir):
        assert load_active_session(temp_project_dir) is None

    def test_loads_session_data(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                    evidence="Test", impact="Impact"),
        ]
        create_session(state)

        data = load_active_session(state.project_path)
        try:
            assert data is not None
            assert data["session_id"] > 0
            assert len(data["findings"]) == 1
            assert data["findings"][0]["severity"] == "major"
        finally:
            if data and "_conn" in data:
                data["_conn"].close()


class TestCompleteAndAbandon:
    def test_complete(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1", status="accepted")]
        create_session(state)

        assert complete_session(state) is True
        s = SessionStore.get(state.db_conn, state.session_id)
        assert s["status"] == "completed"

    def test_complete_returns_false_when_unresolved(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1", status="pending")]
        create_session(state)

        assert complete_session(state) is False
        s = SessionStore.get(state.db_conn, state.session_id)
        assert s["status"] == "active"

    def test_abandon(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)

        abandon_session(state)
        s = SessionStore.get(state.db_conn, state.session_id)
        assert s["status"] == "abandoned"

    def test_complete_active_session(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1", status="accepted")]
        create_session(state)

        assert complete_active_session(state.project_path) is True

    def test_complete_active_session_returns_false_when_unresolved(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1", status="pending")]
        create_session(state)

        assert complete_active_session(state.project_path) is False

    def test_abandon_active_session(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)

        assert abandon_active_session(state.project_path) is True


class TestDeleteAndList:
    def test_delete(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)
        sid = state.session_id

        assert delete_session_by_id(state.project_path, sid) is True
        assert SessionStore.get(state.db_conn, sid) is None

    def test_list_sessions(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)
        # Complete it
        SessionStore.complete(state.db_conn, state.session_id)
        # Create another
        state.session_id = None
        create_session(state)

        sessions = list_sessions(state.project_path)
        assert len(sessions) == 2

    def test_get_detail(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [Finding(number=1, severity="major", lens="prose", location="P1")]
        create_session(state)

        detail = get_session_detail(state.project_path, state.session_id)
        assert detail is not None
        assert len(detail["findings"]) == 1


class TestValidateSession:
    def test_valid(self, sample_session_state):
        data = {
            "scene_path": sample_session_state.scene_path,
            "scene_hash": compute_scene_hash(sample_session_state.scene_content),
        }
        ok, msg = validate_session(data, sample_session_state.scene_content,
                                   sample_session_state.scene_path)
        assert ok is True

    def test_none_data(self):
        ok, msg = validate_session(None, "content", "/path")
        assert ok is False

    def test_modified_content(self, sample_session_state):
        data = {
            "scene_path": sample_session_state.scene_path,
            "scene_hash": compute_scene_hash(sample_session_state.scene_content),
        }
        ok, msg = validate_session(data, "different content", sample_session_state.scene_path)
        assert ok is False
        assert "modified" in msg.lower()


class TestAutoSaveHelpers:
    def test_persist_finding(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        finding = Finding(number=1, severity="major", lens="prose", location="P1")
        state.findings = [finding]
        create_session(state)

        finding.status = "accepted"
        persist_finding(state, finding)

        loaded = FindingStore.get(state.db_conn, state.session_id, 1)
        assert loaded["status"] == "accepted"

    def test_persist_finding_reopens_completed_session(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        finding = Finding(number=1, severity="major", lens="prose", location="P1", status="accepted")
        state.findings = [finding]
        create_session(state)
        assert complete_session(state) is True

        # Revert finding to unresolved and persist; session should auto-reopen
        finding.status = "pending"
        persist_finding(state, finding)

        s = SessionStore.get(state.db_conn, state.session_id)
        assert s["status"] == "active"


class TestCompletionSemantics:
    def test_all_findings_considered_requires_terminal_statuses(self):
        findings = [
            Finding(number=1, severity="major", lens="prose", location="P1", status="accepted"),
            Finding(number=2, severity="major", lens="prose", location="P2", status="pending"),
        ]
        assert all_findings_considered(findings) is False

    def test_persist_index(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)

        persist_session_index(state, 7)
        s = SessionStore.get(state.db_conn, state.session_id)
        assert s["current_index"] == 7

    def test_persist_learning_session(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        create_session(state)

        state.learning.session_rejections.append({"lens": "prose", "pattern": "test"})
        persist_session_learning(state)

        s = SessionStore.get(state.db_conn, state.session_id)
        ls = s["learning_session"]
        assert len(ls["session_rejections"]) == 1

    def test_persist_skipped_without_db(self, sample_session_state):
        """Auto-save should silently skip when no DB connection."""
        finding = Finding(number=1, severity="major", lens="prose", location="P1")
        sample_session_state.findings = [finding]
        # Should not raise
        persist_finding(sample_session_state, finding)
        persist_session_index(sample_session_state, 0)


class TestDetectAndApplySceneChanges:
    async def test_returns_none_when_unchanged(self, sample_session_state):
        result = await detect_and_apply_scene_changes(sample_session_state, 0)
        assert result is None

    async def test_detects_change(self, sample_session_state):
        from unittest.mock import AsyncMock, patch

        finding = Finding(number=1, severity="major", lens="prose",
                         location="P1", line_start=8, line_end=8)
        sample_session_state.findings = [finding]

        scene_path = Path(sample_session_state.scene_path)
        new_content = "New line\n" + sample_session_state.scene_content
        scene_path.write_text(new_content, encoding='utf-8')

        with patch('server.api.re_evaluate_finding', new_callable=AsyncMock):
            result = await detect_and_apply_scene_changes(sample_session_state, 0)

        assert result is not None
        assert result["changed"] is True
        assert sample_session_state.scene_content == new_content

    async def test_returns_none_when_file_missing(self, sample_session_state):
        import os
        os.remove(sample_session_state.scene_path)
        result = await detect_and_apply_scene_changes(sample_session_state, 0)
        assert result is None
