"""Platform-owned SQLite database primitives."""

import logging
import sqlite3
from pathlib import Path

from lit_platform.runtime.config import DB_FILE

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 5


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

    needs_lens_preferences = not _table_has_column(conn, "session", "lens_preferences")
    if current < 3 or needs_lens_preferences:
        _migrate_add_lens_preferences(conn)

    needs_finding_scene_path = not _table_has_column(conn, "finding", "scene_path")
    if current < 4 or needs_finding_scene_path:
        _migrate_add_finding_scene_path(conn)

    needs_index_context_hash = not _table_has_column(conn, "session", "index_context_hash")
    needs_index_context_stale = not _table_has_column(conn, "session", "index_context_stale")
    needs_index_rerun_prompted = not _table_has_column(conn, "session", "index_rerun_prompted")
    needs_index_changed_files = not _table_has_column(conn, "session", "index_changed_files")
    if (
        current < 5
        or needs_index_context_hash
        or needs_index_context_stale
        or needs_index_rerun_prompted
        or needs_index_changed_files
    ):
        _migrate_add_index_context_fields(conn)

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
                   withdrawn_count INTEGER DEFAULT 0
               )"""
        )

        conn.execute(
            """INSERT INTO session_new (
                   id, scene_path, scene_hash, model, discussion_model,
                   lens_preferences,
                   current_index, status, glossary_issues, discussion_history,
                   learning_session, created_at, completed_at, total_findings,
                   accepted_count, rejected_count, withdrawn_count
               )
               SELECT
                   id, scene_path, scene_hash, model, discussion_model,
                   '{}',
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


def _migrate_add_lens_preferences(conn: sqlite3.Connection) -> None:
    """Add ``session.lens_preferences`` when missing."""
    if _table_has_column(conn, "session", "lens_preferences"):
        return

    logger.info("Applying DB migration: add session.lens_preferences")
    conn.execute("ALTER TABLE session ADD COLUMN lens_preferences TEXT DEFAULT '{}' ")
    conn.execute("UPDATE session SET lens_preferences = '{}' WHERE lens_preferences IS NULL")
    conn.commit()


def _migrate_add_finding_scene_path(conn: sqlite3.Connection) -> None:
    """Add ``finding.scene_path`` when missing."""
    if _table_has_column(conn, "finding", "scene_path"):
        return

    logger.info("Applying DB migration: add finding.scene_path")
    conn.execute("ALTER TABLE finding ADD COLUMN scene_path TEXT")
    conn.commit()


def _migrate_add_index_context_fields(conn: sqlite3.Connection) -> None:
    """Add index-context stale detection columns to ``session`` when missing."""
    logger.info("Applying DB migration: add session index-context fields")
    if not _table_has_column(conn, "session", "index_context_hash"):
        conn.execute("ALTER TABLE session ADD COLUMN index_context_hash TEXT DEFAULT ''")
    if not _table_has_column(conn, "session", "index_context_stale"):
        conn.execute("ALTER TABLE session ADD COLUMN index_context_stale INTEGER DEFAULT 0")
    if not _table_has_column(conn, "session", "index_rerun_prompted"):
        conn.execute("ALTER TABLE session ADD COLUMN index_rerun_prompted INTEGER DEFAULT 0")
    if not _table_has_column(conn, "session", "index_changed_files"):
        conn.execute("ALTER TABLE session ADD COLUMN index_changed_files TEXT DEFAULT '[]'")
    conn.commit()


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


__all__ = ["SCHEMA_VERSION", "get_db_path", "get_connection", "init_db"]
