"""Tests for Phase 0 — Finding origin field (tiered analysis architecture).

Covers:
- Finding dataclass: origin field default and custom values
- Finding.to_dict() / from_dict() round-trip with origin
- Backward compatibility: dicts without origin key default to "legacy"
- DB schema migration: existing finding table without origin gets column added
- FindingStore: save_all persists origin, load_all restores it
- Coordinator output: _validate_coordinator_output tags findings with origin="legacy"
"""

import sqlite3
import pytest

from lit_platform.runtime.models import Finding
from lit_platform.runtime.api import _validate_coordinator_output
from lit_platform.persistence.database import init_db, SCHEMA_VERSION, _table_has_column
from lit_platform.persistence.finding_store import FindingStore
from lit_platform.runtime.db import SessionStore


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFindingOriginField:
    """Finding dataclass carries the origin field correctly."""

    def test_default_origin_is_legacy(self):
        """New Finding instances should default origin to 'legacy'."""
        f = Finding(number=1, severity="major", lens="prose", location="P1")
        assert f.origin == "legacy"

    def test_explicit_origin_code(self):
        finding = Finding(number=1, severity="minor", lens="prose",
                          location="P1", origin="code")
        assert finding.origin == "code"

    def test_explicit_origin_checker(self):
        finding = Finding(number=1, severity="major", lens="logic",
                          location="P2", origin="checker")
        assert finding.origin == "checker"

    def test_explicit_origin_critic(self):
        finding = Finding(number=1, severity="critical", lens="prose",
                          location="P3", origin="critic")
        assert finding.origin == "critic"

    def test_to_dict_includes_origin(self):
        """to_dict() must always emit the origin field."""
        f = Finding(number=1, severity="major", lens="prose",
                    location="P1", origin="code")
        d = f.to_dict(include_state=False)
        assert "origin" in d
        assert d["origin"] == "code"

    def test_to_dict_with_state_includes_origin(self):
        f = Finding(number=1, severity="major", lens="prose",
                    location="P1", origin="critic")
        d = f.to_dict(include_state=True)
        assert d["origin"] == "critic"

    def test_from_dict_restores_origin(self):
        d = {"number": 1, "severity": "major", "lens": "prose",
             "location": "P1", "origin": "checker"}
        f = Finding.from_dict(d)
        assert f.origin == "checker"

    def test_from_dict_missing_origin_defaults_to_legacy(self):
        """Dicts without origin (old data) should default to 'legacy'."""
        d = {"number": 1, "severity": "major", "lens": "prose", "location": "P1"}
        f = Finding.from_dict(d)
        assert f.origin == "legacy"

    def test_roundtrip_origin_code(self):
        original = Finding(number=2, severity="minor", lens="clarity",
                           location="P5", origin="code")
        restored = Finding.from_dict(original.to_dict(include_state=True))
        assert restored.origin == "code"

    def test_roundtrip_origin_legacy(self):
        original = Finding(number=3, severity="major", lens="structure",
                           location="P2")  # default origin
        restored = Finding.from_dict(original.to_dict(include_state=True))
        assert restored.origin == "legacy"


# ---------------------------------------------------------------------------
# DB schema migration
# ---------------------------------------------------------------------------

class TestFindingOriginSchemaMigration:
    """Schema migration adds the origin column when absent."""

    def _make_v6_db(self) -> sqlite3.Connection:
        """Build an in-memory DB that looks like it was created before v7
        (no origin column on finding)."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create schema manually without origin column
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_path TEXT NOT NULL,
                scene_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                discussion_model TEXT,
                lens_preferences TEXT DEFAULT '{}',
                current_index INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                glossary_issues TEXT DEFAULT '[]',
                discussion_history TEXT DEFAULT '[]',
                learning_session TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                total_findings INTEGER DEFAULT 0,
                accepted_count INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                withdrawn_count INTEGER DEFAULT 0,
                session_summary TEXT DEFAULT '',
                index_context_hash TEXT DEFAULT '',
                index_context_stale INTEGER DEFAULT 0,
                index_rerun_prompted INTEGER DEFAULT 0,
                index_changed_files TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS finding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
                number INTEGER NOT NULL,
                severity TEXT NOT NULL,
                lens TEXT NOT NULL,
                location TEXT DEFAULT '',
                line_start INTEGER,
                line_end INTEGER,
                scene_path TEXT,
                evidence TEXT DEFAULT '',
                impact TEXT DEFAULT '',
                options TEXT DEFAULT '[]',
                flagged_by TEXT DEFAULT '[]',
                ambiguity_type TEXT,
                stale INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                author_response TEXT DEFAULT '',
                discussion_turns TEXT DEFAULT '[]',
                revision_history TEXT DEFAULT '[]',
                outcome_reason TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS learning (
                id INTEGER PRIMARY KEY,
                project_name TEXT DEFAULT 'Unknown',
                review_count INTEGER DEFAULT 0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS learning_entry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                learning_id INTEGER NOT NULL REFERENCES learning(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                created_at TEXT NOT NULL
            );
            INSERT OR REPLACE INTO schema_version (version) VALUES (6);
        """)
        conn.commit()
        return conn

    def test_origin_column_absent_before_migration(self):
        conn = self._make_v6_db()
        assert not _table_has_column(conn, "finding", "origin")
        conn.close()

    def test_migration_adds_origin_column(self):
        conn = self._make_v6_db()
        init_db(conn)
        assert _table_has_column(conn, "finding", "origin")
        conn.close()

    def test_schema_version_bumped_to_current(self):
        conn = self._make_v6_db()
        init_db(conn)
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == SCHEMA_VERSION  # currently 8
        conn.close()

    def test_migration_drops_legacy_lens_preferences_column(self):
        """v8 cleanup should remove the legacy session.lens_preferences column."""
        conn = self._make_v6_db()
        assert _table_has_column(conn, "session", "lens_preferences")

        init_db(conn)

        assert not _table_has_column(conn, "session", "lens_preferences")
        conn.close()

    def test_session_rows_survive_lens_preferences_drop(self):
        """Session rows should keep core fields after the v8 table rebuild."""
        conn = self._make_v6_db()
        conn.execute(
            "INSERT INTO session (scene_path, scene_hash, model, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            ("/old/scene.md", "oldhash", "sonnet"),
        )
        conn.commit()

        init_db(conn)

        row = conn.execute(
            "SELECT scene_path, scene_hash, model FROM session WHERE scene_path = ?",
            ("/old/scene.md",),
        ).fetchone()
        assert row is not None
        assert row["scene_hash"] == "oldhash"
        assert row["model"] == "sonnet"
        conn.close()

    def test_existing_findings_get_legacy_default(self):
        """Pre-migration findings (no origin column) should read back as 'legacy'."""
        conn = self._make_v6_db()
        # Insert a finding BEFORE migration
        conn.execute(
            "INSERT INTO session (scene_path, scene_hash, model, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            ("/old/scene.md", "oldhash", "sonnet"),
        )
        conn.commit()
        sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO finding (session_id, number, severity, lens) "
            "VALUES (?, 1, 'major', 'prose')",
            (sid,),
        )
        conn.commit()

        # Run migration
        init_db(conn)

        # The old finding should now have origin = 'legacy'
        row = conn.execute(
            "SELECT origin FROM finding WHERE session_id = ?", (sid,)
        ).fetchone()
        assert row is not None
        assert row["origin"] == "legacy"
        conn.close()

    def test_fresh_db_has_origin_column(self, db_conn):
        """A freshly created DB (via fixture) should already have origin column."""
        assert _table_has_column(db_conn, "finding", "origin")


# ---------------------------------------------------------------------------
# FindingStore persistence
# ---------------------------------------------------------------------------

class TestFindingStorePersistsOrigin:
    """FindingStore saves and loads origin correctly."""

    def test_save_and_load_origin_code(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose",
             "origin": "code"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "code"

    def test_save_and_load_origin_checker(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "logic",
             "origin": "checker"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "checker"

    def test_save_and_load_origin_critic(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "critical", "lens": "prose",
             "origin": "critic"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "critic"

    def test_save_without_origin_defaults_to_legacy(self, db_conn):
        """Findings saved without origin key should default to 'legacy'."""
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "minor", "lens": "clarity"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "legacy"

    def test_save_with_legacy_origin(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose",
             "origin": "legacy"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "legacy"

    def test_get_single_includes_origin(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose",
             "origin": "code"},
        ])
        f = FindingStore.get(db_conn, sid, 1)
        assert f is not None
        assert f["origin"] == "code"

    def test_multiple_findings_different_origins(self, db_conn):
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        FindingStore.save_all(db_conn, sid, [
            {"number": 1, "severity": "major", "lens": "prose", "origin": "critic"},
            {"number": 2, "severity": "minor", "lens": "logic", "origin": "checker"},
            {"number": 3, "severity": "minor", "lens": "clarity", "origin": "code"},
        ])
        findings = FindingStore.load_all(db_conn, sid)
        assert findings[0]["origin"] == "critic"
        assert findings[1]["origin"] == "checker"
        assert findings[2]["origin"] == "code"

    def test_finding_to_dict_from_dict_roundtrip_via_store(self, db_conn):
        """Full round-trip: Finding → to_dict → save → load → from_dict → Finding."""
        sid = SessionStore.create(db_conn, "/s.md", "h", "sonnet")
        original = Finding(number=1, severity="major", lens="prose",
                           location="P1", origin="critic")
        FindingStore.save_all(db_conn, sid, [original.to_dict(include_state=True)])

        raw = FindingStore.get(db_conn, sid, 1)
        restored = Finding.from_dict(raw)
        assert restored.origin == "critic"
        assert restored.number == 1
        assert restored.severity == "major"


# ---------------------------------------------------------------------------
# Coordinator output tagging
# ---------------------------------------------------------------------------

class TestCoordinatorOriginTagging:
    """_validate_coordinator_output sets origin='legacy' on all findings."""

    def _make_coordinator_output(self, findings: list[dict]) -> dict:
        return {
            "glossary_issues": [],
            "summary": {
                "prose": {"critical": 0, "major": 0, "minor": 0},
                "structure": {"critical": 0, "major": 0, "minor": 0},
                "coherence": {"critical": 0, "major": 0, "minor": 0},
            },
            "findings": findings,
        }

    def test_findings_get_origin_legacy(self):
        data = self._make_coordinator_output([
            {"number": 1, "severity": "major", "lens": "prose",
             "location": "P1", "evidence": "e", "impact": "i", "options": []},
        ])
        result = _validate_coordinator_output(data)
        assert result["findings"][0]["origin"] == "legacy"

    def test_existing_origin_not_overwritten(self):
        """If a finding already has origin set, setdefault should not overwrite it."""
        data = self._make_coordinator_output([
            {"number": 1, "severity": "major", "lens": "prose",
             "location": "P1", "evidence": "e", "impact": "i", "options": [],
             "origin": "critic"},
        ])
        result = _validate_coordinator_output(data)
        assert result["findings"][0]["origin"] == "critic"

    def test_multiple_findings_all_get_legacy(self):
        data = self._make_coordinator_output([
            {"number": 1, "severity": "major", "lens": "prose",
             "location": "P1", "evidence": "e", "impact": "i", "options": []},
            {"number": 2, "severity": "minor", "lens": "clarity",
             "location": "P2", "evidence": "e2", "impact": "i2", "options": []},
        ])
        result = _validate_coordinator_output(data)
        for f in result["findings"]:
            assert f["origin"] == "legacy"
