"""Tests for lit_platform.services.session_service multi-scene behavior."""

from lit_platform.runtime.db import FindingStore, SessionStore
from lit_platform.runtime.models import Finding
from lit_platform.services import session_service


class TestSessionServiceMultiScene:
    def test_create_session_persists_scene_paths(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene1 = temp_project_dir / "chapter01.md"
        scene2 = temp_project_dir / "chapter02.md"
        scene2.write_text("Second scene", encoding="utf-8")

        state.scene_path = str(scene1)
        state.scene_paths = [str(scene1), str(scene2)]

        sid = session_service.create_session(state)
        row = SessionStore.get(state.db_conn, sid)

        assert row["scene_path"] == str(scene1)
        assert row["scene_paths"] == [str(scene1), str(scene2)]

    def test_persist_finding_saves_scene_path(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene1 = temp_project_dir / "chapter01.md"
        scene2 = temp_project_dir / "chapter02.md"
        scene2.write_text("Second scene", encoding="utf-8")

        finding = Finding(number=1, severity="major", lens="prose", location="P1", scene_path=str(scene1))
        state.findings = [finding]
        session_service.create_session(state)

        finding.scene_path = str(scene2)
        session_service.persist_finding(state, finding)

        stored = FindingStore.get(state.db_conn, state.session_id, 1)
        assert stored["scene_path"] == str(scene2)

    def test_validate_session_accepts_matching_scene_set(self, temp_project_dir):
        scene1 = str((temp_project_dir / "chapter01.md").resolve())
        scene2 = str((temp_project_dir / "chapter02.md").resolve())

        data = {
            "scene_paths": [scene1, scene2],
            "scene_hash": session_service.compute_scene_hash("combined content"),
        }

        ok, msg = session_service.validate_session(
            data,
            "combined content",
            scene1,
            scene_paths=[scene2, scene1],
        )
        assert ok is True

    def test_validate_session_rejects_different_scene_set(self, temp_project_dir):
        scene1 = str((temp_project_dir / "chapter01.md").resolve())
        scene2 = str((temp_project_dir / "chapter02.md").resolve())
        scene3 = str((temp_project_dir / "chapter03.md").resolve())

        data = {
            "scene_paths": [scene1, scene2],
            "scene_hash": session_service.compute_scene_hash("combined content"),
        }

        ok, msg = session_service.validate_session(
            data,
            "combined content",
            scene1,
            scene_paths=[scene1, scene3],
        )
        assert ok is False
        assert "different scene set" in msg.lower()


class TestIndexContextChangeDetection:
    def test_learning_only_change_does_not_mark_stale(self, sample_session_state):
        """LEARNING.md deltas should not trigger index stale/rerun prompts."""
        baseline = session_service.detect_index_context_changes(sample_session_state)
        assert baseline is None

        before_hash = sample_session_state.index_context_hash
        sample_session_state.learning.review_count += 1
        sample_session_state.learning.preferences.append({"description": "[prose] keep sentence fragments"})

        report = session_service.detect_index_context_changes(sample_session_state)

        assert report is None
        assert sample_session_state.index_context_stale is False
        assert sample_session_state.index_changed_files == []
        assert sample_session_state.index_context_hash != before_hash

    def test_real_index_change_still_marks_stale_and_reports_file(self, sample_session_state):
        """Non-learning index changes should keep stale detection behavior."""
        baseline = session_service.detect_index_context_changes(sample_session_state)
        assert baseline is None

        canon_path = sample_session_state.project_path / "CANON.md"
        canon_path.write_text("# Canon\n\nUpdated world rule.", encoding="utf-8")

        report = session_service.detect_index_context_changes(sample_session_state)

        assert report is not None
        assert report["stale"] is True
        assert report["changed"] is True
        assert "CANON.md" in report["changed_files"]
        assert "LEARNING.md" not in report["changed_files"]
