"""
SQLite storage layer for the lit-critic system.

Provides persistent storage for sessions, findings, and learning data
using a per-project SQLite database (``.lit-critic.db``).

All work-in-progress is auto-saved — every mutation is immediately written
to the database, so there is no explicit "save" step.

Module layout::

    get_db_path(project_path) → Path
    get_connection(project_path) → sqlite3.Connection
    init_db(conn)

    SessionStore   — CRUD for review sessions
    FindingStore   — CRUD for findings within a session
    LearningStore  — CRUD for cross-session learning data
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_FILE

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_db_path(project_path: Path) -> Path:
    """Return the path to the project's SQLite database."""
    return project_path / DB_FILE


def get_connection(project_path: Path) -> sqlite3.Connection:
    """Open (or create) the project database and ensure the schema exists.

    Returns a ``sqlite3.Connection`` with WAL mode and foreign keys enabled.
    The caller is responsible for closing the connection.
    """
    db_path = get_db_path(project_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist and apply migrations."""
    conn.executescript(_SCHEMA_SQL)

    # Check / set schema version
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    # Defensive migration path:
    # - Upgrade v1 -> v2 by dropping the legacy session.skip_minor column.
    # - Also run the migration when schema_version is already 2 but the column
    #   still exists (e.g. from an interrupted/partial upgrade).
    needs_skip_minor_drop = _table_has_column(conn, "session", "skip_minor")
    if current < 2 or needs_skip_minor_drop:
        _migrate_drop_skip_minor(conn)

    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if *table* contains *column*."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c[1] == column for c in cols)


def _migrate_drop_skip_minor(conn: sqlite3.Connection) -> None:
    """Drop the legacy ``session.skip_minor`` column while preserving data."""
    if not _table_has_column(conn, "session", "skip_minor"):
        return

    logger.info("Applying DB migration: drop session.skip_minor")
    conn.execute("BEGIN")
    try:
        conn.execute(
            """CREATE TABLE session_new (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   scene_path TEXT NOT NULL,
                   scene_hash TEXT NOT NULL,
                   model TEXT NOT NULL,
                   discussion_model TEXT,
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
                   withdrawn_count INTEGER DEFAULT 0
               )"""
        )

        conn.execute(
            """INSERT INTO session_new (
                   id, scene_path, scene_hash, model, discussion_model,
                   current_index, status, glossary_issues, discussion_history,
                   learning_session, created_at, completed_at, total_findings,
                   accepted_count, rejected_count, withdrawn_count
               )
               SELECT
                   id, scene_path, scene_hash, model, discussion_model,
                   current_index, status, glossary_issues, discussion_history,
                   learning_session, created_at, completed_at, total_findings,
                   accepted_count, rejected_count, withdrawn_count
               FROM session"""
        )

        conn.execute("DROP TABLE session")
        conn.execute("ALTER TABLE session_new RENAME TO session")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_path TEXT NOT NULL,
    scene_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    discussion_model TEXT,
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
    withdrawn_count INTEGER DEFAULT 0
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

CREATE INDEX IF NOT EXISTS idx_finding_session ON finding(session_id);

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
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_learning_entry_category ON learning_entry(category);
"""


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """CRUD operations for review sessions."""

    @staticmethod
    def create(conn: sqlite3.Connection, scene_path: str, scene_hash: str,
               model: str, glossary_issues: list[str] | None = None,
               discussion_model: str | None = None) -> int:
        """Insert a new active session. Returns the session id."""
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """INSERT INTO session
               (scene_path, scene_hash, model, discussion_model, glossary_issues, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scene_path, scene_hash, model, discussion_model,
             json.dumps(glossary_issues or []), now),
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def load_active(conn: sqlite3.Connection) -> Optional[dict]:
        """Load the active session, or None if no active session exists."""
        row = conn.execute(
            "SELECT * FROM session WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return SessionStore._row_to_dict(row)

    @staticmethod
    def exists_active(conn: sqlite3.Connection) -> bool:
        """Check whether an active session exists."""
        row = conn.execute(
            "SELECT 1 FROM session WHERE status = 'active' LIMIT 1"
        ).fetchone()
        return row is not None

    @staticmethod
    def get(conn: sqlite3.Connection, session_id: int) -> Optional[dict]:
        """Load a single session by id."""
        row = conn.execute(
            "SELECT * FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return SessionStore._row_to_dict(row)

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> list[dict]:
        """List all sessions, newest first."""
        rows = conn.execute(
            "SELECT * FROM session ORDER BY id DESC"
        ).fetchall()
        return [SessionStore._row_to_dict(r) for r in rows]

    @staticmethod
    def update_index(conn: sqlite3.Connection, session_id: int,
                     current_index: int) -> None:
        """Update the current finding index (auto-save on navigate)."""
        conn.execute(
            "UPDATE session SET current_index = ? WHERE id = ?",
            (current_index, session_id),
        )
        conn.commit()

    @staticmethod
    def update_glossary_issues(conn: sqlite3.Connection, session_id: int,
                               glossary_issues: list[str]) -> None:
        """Update glossary issues."""
        conn.execute(
            "UPDATE session SET glossary_issues = ? WHERE id = ?",
            (json.dumps(glossary_issues), session_id),
        )
        conn.commit()

    @staticmethod
    def update_discussion_history(conn: sqlite3.Connection, session_id: int,
                                  discussion_history: list[dict]) -> None:
        """Update discussion history."""
        conn.execute(
            "UPDATE session SET discussion_history = ? WHERE id = ?",
            (json.dumps(discussion_history), session_id),
        )
        conn.commit()

    @staticmethod
    def update_learning_session(conn: sqlite3.Connection, session_id: int,
                                learning_session: dict) -> None:
        """Update the in-session learning data (rejections, acceptances, etc.)."""
        conn.execute(
            "UPDATE session SET learning_session = ? WHERE id = ?",
            (json.dumps(learning_session), session_id),
        )
        conn.commit()

    @staticmethod
    def update_scene(conn: sqlite3.Connection, session_id: int,
                     scene_hash: str) -> None:
        """Update scene hash after a scene change detection."""
        conn.execute(
            "UPDATE session SET scene_hash = ? WHERE id = ?",
            (scene_hash, session_id),
        )
        conn.commit()

    @staticmethod
    def update_scene_path(conn: sqlite3.Connection, session_id: int,
                          scene_path: str) -> None:
        """Update the persisted scene path for a session."""
        conn.execute(
            "UPDATE session SET scene_path = ? WHERE id = ?",
            (scene_path, session_id),
        )
        conn.commit()

    @staticmethod
    def update_counts(conn: sqlite3.Connection, session_id: int) -> None:
        """Recalculate and update finding counts for a session.
        
        Called after a finding status changes to keep the session's
        accepted_count, rejected_count, and withdrawn_count up-to-date
        during an active session.
        """
        stats = conn.execute(
            """SELECT
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS accepted,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                   SUM(CASE WHEN status = 'withdrawn' THEN 1 ELSE 0 END) AS withdrawn
               FROM finding WHERE session_id = ?""",
            (session_id,),
        ).fetchone()

        conn.execute(
            """UPDATE session SET
                   accepted_count = ?,
                   rejected_count = ?,
                   withdrawn_count = ?
               WHERE id = ?""",
            (stats["accepted"], stats["rejected"], stats["withdrawn"], session_id),
        )
        conn.commit()

    @staticmethod
    def complete(conn: sqlite3.Connection, session_id: int) -> None:
        """Mark a session as completed and tally stats from its findings."""
        now = datetime.now().isoformat()

        # Tally finding stats
        stats = conn.execute(
            """SELECT
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS accepted,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                   SUM(CASE WHEN status = 'withdrawn' THEN 1 ELSE 0 END) AS withdrawn
               FROM finding WHERE session_id = ?""",
            (session_id,),
        ).fetchone()

        conn.execute(
            """UPDATE session SET
                   status = 'completed', completed_at = ?,
                   total_findings = ?, accepted_count = ?,
                   rejected_count = ?, withdrawn_count = ?
               WHERE id = ?""",
            (now, stats["total"], stats["accepted"],
             stats["rejected"], stats["withdrawn"], session_id),
        )
        conn.commit()

    @staticmethod
    def reopen(conn: sqlite3.Connection, session_id: int) -> None:
        """Re-open a completed session back to active status.

        Used when completion was previously recorded but a finding is later
        moved back to a non-terminal state.
        """
        conn.execute(
            "UPDATE session SET status = 'active', completed_at = NULL WHERE id = ?",
            (session_id,),
        )
        conn.commit()

    @staticmethod
    def abandon(conn: sqlite3.Connection, session_id: int) -> None:
        """Mark a session as abandoned."""
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE session SET status = 'abandoned', completed_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()

    @staticmethod
    def delete(conn: sqlite3.Connection, session_id: int) -> bool:
        """Delete a session and its findings. Returns True if a row was deleted."""
        cursor = conn.execute(
            "DELETE FROM session WHERE id = ?", (session_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def validate(session_data: dict, scene_content_hash: str,
                 scene_path: str) -> tuple[bool, str]:
        """Validate that a saved session matches the current scene.

        Returns ``(is_valid, error_message)``.
        """
        if not session_data:
            return False, "No session data"

        saved_scene_path = session_data.get("scene_path", "")
        if Path(saved_scene_path).resolve() != Path(scene_path).resolve():
            return False, f"Session is for different scene: {saved_scene_path}"

        saved_hash = session_data.get("scene_hash", "")
        if saved_hash != scene_content_hash:
            return False, "Scene file has been modified since session was saved"

        return True, ""

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a plain dict, deserialising JSON columns."""
        d = dict(row)
        for key in ("glossary_issues", "discussion_history"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        if "learning_session" in d and isinstance(d["learning_session"], str):
            try:
                d["learning_session"] = json.loads(d["learning_session"])
            except (json.JSONDecodeError, TypeError):
                d["learning_session"] = {}
        # Convert integer booleans
        if "stale" in d:
            d["stale"] = bool(d["stale"])
        return d


# ---------------------------------------------------------------------------
# FindingStore
# ---------------------------------------------------------------------------


class FindingStore:
    """CRUD operations for findings within a session."""

    @staticmethod
    def save_all(conn: sqlite3.Connection, session_id: int,
                 findings: list[dict]) -> None:
        """Insert all findings for a session (bulk insert after analysis).

        Each dict should match the Finding.to_dict(include_state=True) shape.
        """
        rows = []
        for f in findings:
            rows.append((
                session_id,
                f.get("number", 0),
                f.get("severity", "minor"),
                f.get("lens", "unknown"),
                f.get("location", ""),
                f.get("line_start"),
                f.get("line_end"),
                f.get("evidence", ""),
                f.get("impact", ""),
                json.dumps(f.get("options", [])),
                json.dumps(f.get("flagged_by", [])),
                f.get("ambiguity_type"),
                int(f.get("stale", False)),
                f.get("status", "pending"),
                f.get("author_response", ""),
                json.dumps(f.get("discussion_turns", [])),
                json.dumps(f.get("revision_history", [])),
                f.get("outcome_reason", ""),
            ))

        conn.executemany(
            """INSERT INTO finding
               (session_id, number, severity, lens, location,
                line_start, line_end, evidence, impact, options,
                flagged_by, ambiguity_type, stale, status,
                author_response, discussion_turns, revision_history,
                outcome_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    @staticmethod
    def load_all(conn: sqlite3.Connection, session_id: int) -> list[dict]:
        """Load all findings for a session, ordered by number."""
        rows = conn.execute(
            "SELECT * FROM finding WHERE session_id = ? ORDER BY number",
            (session_id,),
        ).fetchall()
        return [FindingStore._row_to_dict(r) for r in rows]

    @staticmethod
    def get(conn: sqlite3.Connection, session_id: int,
            number: int) -> Optional[dict]:
        """Load a single finding by session and number."""
        row = conn.execute(
            "SELECT * FROM finding WHERE session_id = ? AND number = ?",
            (session_id, number),
        ).fetchone()
        if row is None:
            return None
        return FindingStore._row_to_dict(row)

    @staticmethod
    def update(conn: sqlite3.Connection, session_id: int, number: int,
               **fields) -> None:
        """Update specific fields of a finding.

        JSON-serialisable fields (``options``, ``flagged_by``,
        ``discussion_turns``, ``revision_history``) are automatically
        serialised.  The ``stale`` field is converted to int.
        """
        if not fields:
            return

        json_fields = {"options", "flagged_by", "discussion_turns", "revision_history"}
        set_clauses = []
        values = []
        for key, value in fields.items():
            set_clauses.append(f"{key} = ?")
            if key in json_fields:
                values.append(json.dumps(value))
            elif key == "stale":
                values.append(int(value))
            else:
                values.append(value)

        values.extend([session_id, number])
        sql = f"UPDATE finding SET {', '.join(set_clauses)} WHERE session_id = ? AND number = ?"
        conn.execute(sql, values)
        conn.commit()

    @staticmethod
    def update_by_id(conn: sqlite3.Connection, finding_id: int,
                     **fields) -> None:
        """Update specific fields of a finding by its primary key."""
        if not fields:
            return

        json_fields = {"options", "flagged_by", "discussion_turns", "revision_history"}
        set_clauses = []
        values = []
        for key, value in fields.items():
            set_clauses.append(f"{key} = ?")
            if key in json_fields:
                values.append(json.dumps(value))
            elif key == "stale":
                values.append(int(value))
            else:
                values.append(value)

        values.append(finding_id)
        sql = f"UPDATE finding SET {', '.join(set_clauses)} WHERE id = ?"
        conn.execute(sql, values)
        conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Convert a finding row to a plain dict, deserialising JSON columns."""
        d = dict(row)
        for key in ("options", "flagged_by", "discussion_turns", "revision_history"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        if "stale" in d:
            d["stale"] = bool(d["stale"])
        return d


# ---------------------------------------------------------------------------
# LearningStore
# ---------------------------------------------------------------------------

# Category constants
CATEGORY_PREFERENCE = "preference"
CATEGORY_BLIND_SPOT = "blind_spot"
CATEGORY_RESOLUTION = "resolution"
CATEGORY_AMBIGUITY_INTENTIONAL = "ambiguity_intentional"
CATEGORY_AMBIGUITY_ACCIDENTAL = "ambiguity_accidental"

ALL_CATEGORIES = (
    CATEGORY_PREFERENCE,
    CATEGORY_BLIND_SPOT,
    CATEGORY_RESOLUTION,
    CATEGORY_AMBIGUITY_INTENTIONAL,
    CATEGORY_AMBIGUITY_ACCIDENTAL,
)


class LearningStore:
    """CRUD operations for cross-session learning data."""

    @staticmethod
    def ensure_exists(conn: sqlite3.Connection,
                      project_name: str = "Unknown") -> int:
        """Ensure a learning record exists, creating one if needed.

        Returns the learning id.
        """
        row = conn.execute("SELECT id FROM learning LIMIT 1").fetchone()
        if row:
            return row["id"]

        now = datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO learning (project_name, updated_at) VALUES (?, ?)",
            (project_name, now),
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def load(conn: sqlite3.Connection) -> dict:
        """Load learning data as a dict with entries grouped by category.

        Returns::

            {
                "id": 1,
                "project_name": "...",
                "review_count": 5,
                "preferences": [{"id": 1, "description": "..."}],
                "blind_spots": [...],
                "resolutions": [...],
                "ambiguity_intentional": [...],
                "ambiguity_accidental": [...],
            }
        """
        row = conn.execute("SELECT * FROM learning LIMIT 1").fetchone()
        if row is None:
            return {
                "id": None,
                "project_name": "Unknown",
                "review_count": 0,
                "preferences": [],
                "blind_spots": [],
                "resolutions": [],
                "ambiguity_intentional": [],
                "ambiguity_accidental": [],
            }

        result = dict(row)
        for cat in ALL_CATEGORIES:
            entries = conn.execute(
                "SELECT id, description, created_at FROM learning_entry "
                "WHERE learning_id = ? AND category = ? ORDER BY id",
                (row["id"], cat),
            ).fetchall()
            result[cat if cat != "blind_spot" else "blind_spots"] = [
                dict(e) for e in entries
            ]

        # Normalise key names to match LearningData field names
        if "preference" in result:
            result["preferences"] = result.pop("preference")
        if "blind_spot" in result:
            result["blind_spots"] = result.pop("blind_spot")
        if "resolution" in result:
            result["resolutions"] = result.pop("resolution")

        return result

    @staticmethod
    def save_from_learning_data(conn: sqlite3.Connection,
                                learning_data) -> None:
        """Persist a ``LearningData`` object to the database.

        This replaces all entries with the current state of the
        ``LearningData``, useful after ``update_learning_from_session()``.
        """
        learning_id = LearningStore.ensure_exists(
            conn, learning_data.project_name
        )
        now = datetime.now().isoformat()

        conn.execute(
            "UPDATE learning SET project_name = ?, review_count = ?, updated_at = ? WHERE id = ?",
            (learning_data.project_name, learning_data.review_count, now, learning_id),
        )

        # Replace all entries
        conn.execute(
            "DELETE FROM learning_entry WHERE learning_id = ?", (learning_id,)
        )

        entries = []
        for desc_dict in learning_data.preferences:
            desc = desc_dict.get("description", str(desc_dict))
            entries.append((learning_id, CATEGORY_PREFERENCE, desc, now))
        for desc_dict in learning_data.blind_spots:
            desc = desc_dict.get("description", str(desc_dict))
            entries.append((learning_id, CATEGORY_BLIND_SPOT, desc, now))
        for desc_dict in learning_data.resolutions:
            desc = desc_dict.get("description", str(desc_dict))
            entries.append((learning_id, CATEGORY_RESOLUTION, desc, now))
        for desc_dict in learning_data.ambiguity_intentional:
            desc = desc_dict.get("description", str(desc_dict))
            entries.append((learning_id, CATEGORY_AMBIGUITY_INTENTIONAL, desc, now))
        for desc_dict in learning_data.ambiguity_accidental:
            desc = desc_dict.get("description", str(desc_dict))
            entries.append((learning_id, CATEGORY_AMBIGUITY_ACCIDENTAL, desc, now))

        if entries:
            conn.executemany(
                "INSERT INTO learning_entry (learning_id, category, description, created_at) "
                "VALUES (?, ?, ?, ?)",
                entries,
            )

        conn.commit()

    @staticmethod
    def add_entry(conn: sqlite3.Connection, category: str,
                  description: str) -> int:
        """Add a single learning entry. Returns the entry id."""
        learning_id = LearningStore.ensure_exists(conn)
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO learning_entry (learning_id, category, description, created_at) "
            "VALUES (?, ?, ?, ?)",
            (learning_id, category, description, now),
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def add_preference(conn: sqlite3.Connection, description: str) -> int:
        """Add a preference entry. Returns the entry id."""
        return LearningStore.add_entry(conn, CATEGORY_PREFERENCE, description)

    @staticmethod
    def add_blind_spot(conn: sqlite3.Connection, description: str) -> int:
        """Add a blind spot entry. Returns the entry id."""
        return LearningStore.add_entry(conn, CATEGORY_BLIND_SPOT, description)

    @staticmethod
    def add_resolution(conn: sqlite3.Connection, description: str) -> int:
        """Add a resolution entry. Returns the entry id."""
        return LearningStore.add_entry(conn, CATEGORY_RESOLUTION, description)

    @staticmethod
    def add_ambiguity(conn: sqlite3.Connection, description: str,
                      intentional: bool = True) -> int:
        """Add an ambiguity entry (intentional or accidental). Returns the entry id."""
        category = CATEGORY_AMBIGUITY_INTENTIONAL if intentional else CATEGORY_AMBIGUITY_ACCIDENTAL
        return LearningStore.add_entry(conn, category, description)

    @staticmethod
    def remove_entry(conn: sqlite3.Connection, entry_id: int) -> bool:
        """Delete a single learning entry. Returns True if deleted."""
        cursor = conn.execute(
            "DELETE FROM learning_entry WHERE id = ?", (entry_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def list_entries(conn: sqlite3.Connection,
                     category: str | None = None) -> list[dict]:
        """List learning entries, optionally filtered by category."""
        if category:
            rows = conn.execute(
                "SELECT le.*, l.project_name FROM learning_entry le "
                "JOIN learning l ON le.learning_id = l.id "
                "WHERE le.category = ? ORDER BY le.id",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT le.*, l.project_name FROM learning_entry le "
                "JOIN learning l ON le.learning_id = l.id "
                "ORDER BY le.category, le.id",
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def increment_review_count(conn: sqlite3.Connection) -> None:
        """Increment the review count by 1."""
        learning_id = LearningStore.ensure_exists(conn)
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE learning SET review_count = review_count + 1, updated_at = ? WHERE id = ?",
            (now, learning_id),
        )
        conn.commit()

    @staticmethod
    def reset(conn: sqlite3.Connection) -> None:
        """Delete all learning data."""
        conn.execute("DELETE FROM learning_entry")
        conn.execute("DELETE FROM learning")
        conn.commit()

    @staticmethod
    def export_markdown(conn: sqlite3.Connection) -> str:
        """Generate LEARNING.md content from the database."""
        data = LearningStore.load(conn)

        lines = [
            "# Learning",
            "",
            f"PROJECT: {data.get('project_name', 'Unknown')}",
            f"LAST_UPDATED: {datetime.now().strftime('%Y-%m-%d')}",
            f"REVIEW_COUNT: {data.get('review_count', 0)}",
            "",
            "## Preferences",
            "",
        ]

        prefs = data.get("preferences", [])
        if prefs:
            for p in prefs:
                lines.append(f"- {p.get('description', p)}")
        else:
            lines.append("[none yet]")

        lines.extend(["", "## Blind Spots", ""])
        spots = data.get("blind_spots", [])
        if spots:
            for s in spots:
                lines.append(f"- {s.get('description', s)}")
        else:
            lines.append("[none yet]")

        lines.extend(["", "## Resolutions", ""])
        resolutions = data.get("resolutions", [])
        if resolutions:
            for r in resolutions:
                lines.append(f"- {r.get('description', r)}")
        else:
            lines.append("[none yet]")

        lines.extend(["", "## Ambiguity Patterns", "", "### Intentional", ""])
        intentional = data.get("ambiguity_intentional", [])
        if intentional:
            for a in intentional:
                lines.append(f"- {a.get('description', a)}")
        else:
            lines.append("[none yet]")

        lines.extend(["", "### Accidental", ""])
        accidental = data.get("ambiguity_accidental", [])
        if accidental:
            for a in accidental:
                lines.append(f"- {a.get('description', a)}")
        else:
            lines.append("[none yet]")

        return "\n".join(lines)
