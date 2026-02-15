"""
Tests for the server.db SQLite storage layer.
"""

import pytest
from server.db import SessionStore, FindingStore, LearningStore, CATEGORY_PREFERENCE, CATEGORY_BLIND_SPOT
from server.models import LearningData


class TestSessionStore:
    """Tests for SessionStore CRUD operations."""

    def test_create_returns_id(self, db_conn):
        sid = SessionStore.create(db_conn, "/path/scene.md", "abc123", "sonnet")
        assert isinstance(sid, int)
        assert sid > 0

    def test_load_active(self, db_conn):
        SessionStore.create(db_conn, "/path/scene.md", "abc", "sonnet")
        active = SessionStore.load_active(db_conn)
        assert active is not None
        assert active["scene_path"] == "/path/scene.md"
        assert active["status"] == "active"

    def test_load_active_returns_none_when_empty(self, db_conn):
        assert SessionStore.load_active(db_conn) is None

    def test_exists_active(self, db_conn):
        assert SessionStore.exists_active(db_conn) is False
        SessionStore.create(db_conn, "/p/s.md", "h", "sonnet")
        assert SessionStore.exists_active(db_conn) is True

    def test_complete_sets_status_and_stats(self, db_conn):
        sid = SessionStore.create(db_conn, "/p/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose", "status": "accepted"},
            {"number": 2, "severity": "minor", "lens": "clarity", "status": "rejected"},
        ])
        SessionStore.complete(db_conn, sid)
        s = SessionStore.get(db_conn, sid)
        assert s["status"] == "completed"
        assert s["total_findings"] == 2
        assert s["accepted_count"] == 1
        assert s["rejected_count"] == 1
        assert s["completed_at"] is not None

    def test_abandon(self, db_conn):
        sid = SessionStore.create(db_conn, "/p/s.md", "h", "sonnet")
        SessionStore.abandon(db_conn, sid)
        s = SessionStore.get(db_conn, sid)
        assert s["status"] == "abandoned"

    def test_delete(self, db_conn):
        sid = SessionStore.create(db_conn, "/p/s.md", "h", "sonnet")
        assert SessionStore.delete(db_conn, sid) is True
        assert SessionStore.get(db_conn, sid) is None

    def test_delete_nonexistent(self, db_conn):
        assert SessionStore.delete(db_conn, 999) is False

    def test_list_all(self, db_conn):
        SessionStore.create(db_conn, "/a.md", "h1", "sonnet")
        SessionStore.create(db_conn, "/b.md", "h2", "haiku")
        sessions = SessionStore.list_all(db_conn)
        assert len(sessions) == 2
        assert sessions[0]["id"] > sessions[1]["id"]  # newest first

    def test_update_index(self, db_conn):
        sid = SessionStore.create(db_conn, "/p/s.md", "h", "sonnet")
        SessionStore.update_index(db_conn, sid, 5)
        s = SessionStore.get(db_conn, sid)
        assert s["current_index"] == 5

    def test_update_scene_path(self, db_conn):
        sid = SessionStore.create(db_conn, "/old/path/scene.md", "h", "sonnet")
        SessionStore.update_scene_path(db_conn, sid, "/new/path/scene.md")
        s = SessionStore.get(db_conn, sid)
        assert s["scene_path"] == "/new/path/scene.md"

    def test_validate_valid(self, db_conn):
        ok, msg = SessionStore.validate(
            {"scene_path": "/a/b.md", "scene_hash": "xyz"},
            scene_content_hash="xyz", scene_path="/a/b.md",
        )
        assert ok is True

    def test_validate_different_path(self, db_conn):
        ok, msg = SessionStore.validate(
            {"scene_path": "/a/b.md", "scene_hash": "xyz"},
            scene_content_hash="xyz", scene_path="/c/d.md",
        )
        assert ok is False
        assert "different scene" in msg.lower()

    def test_validate_different_hash(self, db_conn):
        ok, msg = SessionStore.validate(
            {"scene_path": "/a/b.md", "scene_hash": "xyz"},
            scene_content_hash="abc", scene_path="/a/b.md",
        )
        assert ok is False
        assert "modified" in msg.lower()


class TestFindingStore:
    """Tests for FindingStore CRUD operations."""

    def test_save_and_load_all(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose",
             "evidence": "Test", "options": ["Fix"]},
            {"number": 2, "severity": "minor", "lens": "clarity"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert len(findings) == 2
        assert findings[0]["number"] == 1
        assert findings[0]["options"] == ["Fix"]
        assert findings[1]["severity"] == "minor"

    def test_get_single(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose"},
        ])
        f = FindingStore.get(db_conn, sid, 1)
        assert f is not None
        assert f["severity"] == "major"

    def test_get_nonexistent(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        assert FindingStore.get(db_conn, sid, 99) is None

    def test_update(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose", "status": "pending"},
        ])
        FindingStore.update(db_conn, sid, 1, status="accepted", severity="minor")
        f = FindingStore.get(db_conn, sid, 1)
        assert f["status"] == "accepted"
        assert f["severity"] == "minor"

    def test_update_json_fields(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose"},
        ])
        FindingStore.update(db_conn, sid, 1,
                           discussion_turns=[{"role": "user", "content": "hi"}],
                           options=["A", "B"])
        f = FindingStore.get(db_conn, sid, 1)
        assert len(f["discussion_turns"]) == 1
        assert f["options"] == ["A", "B"]

    def test_cascade_delete(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose"},
        ])
        SessionStore.delete(db_conn, sid)
        assert FindingStore.load_all(db_conn, sid) == []


class TestLearningStore:
    """Tests for LearningStore CRUD operations."""

    def test_ensure_exists_creates(self, db_conn):
        lid = LearningStore.ensure_exists(db_conn, "My Novel")
        assert isinstance(lid, int)
        # Calling again returns same id
        lid2 = LearningStore.ensure_exists(db_conn)
        assert lid == lid2

    def test_load_empty(self, db_conn):
        data = LearningStore.load(db_conn)
        assert data["id"] is None
        assert data["preferences"] == []

    def test_save_and_load(self, db_conn):
        ld = LearningData(project_name="Test", review_count=5)
        ld.preferences.append({"description": "Pref 1"})
        ld.blind_spots.append({"description": "Blind 1"})
        LearningStore.save_from_learning_data(db_conn, ld)

        data = LearningStore.load(db_conn)
        assert data["project_name"] == "Test"
        assert data["review_count"] == 5
        assert len(data["preferences"]) == 1
        assert len(data["blind_spots"]) == 1

    def test_add_entry(self, db_conn):
        eid = LearningStore.add_entry(db_conn, CATEGORY_PREFERENCE, "Test pref")
        assert isinstance(eid, int)
        entries = LearningStore.list_entries(db_conn, CATEGORY_PREFERENCE)
        assert len(entries) == 1
        assert entries[0]["description"] == "Test pref"

    def test_remove_entry(self, db_conn):
        eid = LearningStore.add_entry(db_conn, CATEGORY_PREFERENCE, "Test")
        assert LearningStore.remove_entry(db_conn, eid) is True
        assert LearningStore.list_entries(db_conn, CATEGORY_PREFERENCE) == []

    def test_increment_review_count(self, db_conn):
        LearningStore.ensure_exists(db_conn)
        LearningStore.increment_review_count(db_conn)
        LearningStore.increment_review_count(db_conn)
        data = LearningStore.load(db_conn)
        assert data["review_count"] == 2

    def test_reset(self, db_conn):
        ld = LearningData(project_name="Test", review_count=3)
        ld.preferences.append({"description": "Pref"})
        LearningStore.save_from_learning_data(db_conn, ld)

        LearningStore.reset(db_conn)
        data = LearningStore.load(db_conn)
        assert data["id"] is None

    def test_export_markdown(self, db_conn):
        ld = LearningData(project_name="Novel", review_count=2)
        ld.preferences.append({"description": "[prose] Test preference"})
        LearningStore.save_from_learning_data(db_conn, ld)

        md = LearningStore.export_markdown(db_conn)
        assert "# Learning" in md
        assert "PROJECT: Novel" in md
        assert "REVIEW_COUNT: 2" in md
        assert "- [prose] Test preference" in md
