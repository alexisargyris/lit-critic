"""Platform-owned SQLite database primitives."""

import json
import logging
import sqlite3
from pathlib import Path

from lit_platform.runtime.config import DB_FILE

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 17


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
    _migrate_relativize_paths(conn, project_path)
    return conn


def get_passive_connection(project_path: Path) -> sqlite3.Connection | None:
    """Open an existing project database without initialization side effects.

    This startup-safe path avoids WAL setup, schema initialization, and
    migrations. If the database file does not exist yet, ``None`` is returned
    so passive reads do not create a database as a side effect.

    The returned connection is configured for row access and query-only mode.
    The caller is responsible for closing the connection.
    """
    db_path = get_db_path(project_path)
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
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

    has_legacy_lens_preferences = _table_has_column(conn, "session", "lens_preferences")
    needs_lens_preferences = not has_legacy_lens_preferences
    # ``lens_preferences`` existed only in schema v3-v7 and was removed in v8.
    # Do not resurrect it for modern schemas (>= v8), otherwise every
    # connection would re-add then re-drop the column, rewriting ``session``.
    if current < 8 and needs_lens_preferences:
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

    needs_learning_confidence = not _table_has_column(conn, "learning_entry", "confidence")
    needs_session_summary = not _table_has_column(conn, "session", "session_summary")
    if current < 6 or needs_learning_confidence or needs_session_summary:
        _migrate_add_confidence_and_session_summary(conn)

    needs_finding_origin = not _table_has_column(conn, "finding", "origin")
    if current < 7 or needs_finding_origin:
        _migrate_add_finding_origin(conn)

    if current < 8 or has_legacy_lens_preferences:
        _migrate_drop_lens_preferences(conn)

    needs_depth_mode = not _table_has_column(conn, "session", "depth_mode")
    needs_frontier_model = not _table_has_column(conn, "session", "frontier_model")
    needs_checker_model = not _table_has_column(conn, "session", "checker_model")
    if current < 9 or needs_depth_mode or needs_frontier_model or needs_checker_model:
        _migrate_add_tier_model_fields(conn)

    needs_scene_projection = not _table_exists(conn, "scene_projection")
    if current < 10 or needs_scene_projection:
        _migrate_add_scene_projection(conn)

    needs_index_projection = not _table_exists(conn, "index_projection")
    if current < 11 or needs_index_projection:
        _migrate_add_index_projection(conn)

    needs_extracted_scene_metadata = not _table_exists(
        conn, "extracted_scene_metadata"
    )
    needs_extracted_characters = not _table_exists(conn, "extracted_characters")
    needs_extracted_terms = not _table_exists(conn, "extracted_terms")
    needs_extracted_threads = not _table_exists(conn, "extracted_threads")
    needs_extracted_thread_events = not _table_exists(conn, "extracted_thread_events")
    needs_extracted_timeline = not _table_exists(conn, "extracted_timeline")
    needs_knowledge_overrides = not _table_exists(conn, "knowledge_overrides")
    if (
        current < 12
        or needs_extracted_scene_metadata
        or needs_extracted_characters
        or needs_extracted_terms
        or needs_extracted_threads
        or needs_extracted_thread_events
        or needs_extracted_timeline
        or needs_knowledge_overrides
    ):
        _migrate_add_extracted_knowledge(conn)

    needs_entity_locked_characters = not _table_has_column(conn, "extracted_characters", "entity_locked")
    needs_entity_locked_terms = not _table_has_column(conn, "extracted_terms", "entity_locked")
    needs_entity_locked_threads = not _table_has_column(conn, "extracted_threads", "entity_locked")
    needs_entity_locked_timeline = not _table_has_column(conn, "extracted_timeline", "entity_locked")
    if (
        current < 14
        or needs_entity_locked_characters
        or needs_entity_locked_terms
        or needs_entity_locked_threads
        or needs_entity_locked_timeline
    ):
        _migrate_add_entity_locking(conn)

    needs_character_sources = not _table_exists(conn, "extracted_character_sources")
    needs_term_sources = not _table_exists(conn, "extracted_term_sources")
    if current < 15 or needs_character_sources or needs_term_sources:
        _migrate_add_source_tables(conn)

    needs_review_flags = not _table_exists(conn, "knowledge_review_flags")
    if current < 16 or needs_review_flags:
        _migrate_add_knowledge_review_flags(conn)

    needs_staleness_cache = not _table_exists(conn, "knowledge_staleness_cache")
    if current < 17 or needs_staleness_cache:
        _migrate_add_knowledge_staleness_cache(conn)

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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if *table* exists in the current database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


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


def _migrate_add_finding_origin(conn: sqlite3.Connection) -> None:
    """Add ``finding.origin`` when missing (v7 — tiered analysis architecture)."""
    if _table_has_column(conn, "finding", "origin"):
        return

    logger.info("Applying DB migration: add finding.origin")
    conn.execute("ALTER TABLE finding ADD COLUMN origin TEXT DEFAULT 'legacy'")
    conn.execute("UPDATE finding SET origin = 'legacy' WHERE origin IS NULL")
    conn.commit()


def _migrate_drop_lens_preferences(conn: sqlite3.Connection) -> None:
    """Drop legacy ``session.lens_preferences`` column (v8 cleanup)."""
    if not _table_has_column(conn, "session", "lens_preferences"):
        return

    logger.info("Applying DB migration: drop session.lens_preferences")
    conn.execute("PRAGMA foreign_keys=OFF")
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
                   withdrawn_count INTEGER DEFAULT 0,
                   session_summary TEXT DEFAULT '',
                   index_context_hash TEXT DEFAULT '',
                   index_context_stale INTEGER DEFAULT 0,
                   index_rerun_prompted INTEGER DEFAULT 0,
                   index_changed_files TEXT DEFAULT '[]'
               )"""
        )

        conn.execute(
            """INSERT INTO session_new (
                   id, scene_path, scene_hash, model, discussion_model,
                   current_index, status, glossary_issues, discussion_history,
                   learning_session, created_at, completed_at, total_findings,
                   accepted_count, rejected_count, withdrawn_count,
                   session_summary, index_context_hash, index_context_stale,
                   index_rerun_prompted, index_changed_files
               )
               SELECT
                   id, scene_path, scene_hash, model, discussion_model,
                   current_index, status, glossary_issues, discussion_history,
                   learning_session, created_at, completed_at, total_findings,
                   accepted_count, rejected_count, withdrawn_count,
                   session_summary, index_context_hash, index_context_stale,
                   index_rerun_prompted, index_changed_files
               FROM session"""
        )

        conn.execute("DROP TABLE session")
        conn.execute("ALTER TABLE session_new RENAME TO session")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _migrate_add_confidence_and_session_summary(conn: sqlite3.Connection) -> None:
    """Add v6 anti-sycophancy columns for learning confidence and session summary."""
    logger.info("Applying DB migration: add learning confidence + session summary")
    if not _table_has_column(conn, "learning_entry", "confidence"):
        conn.execute("ALTER TABLE learning_entry ADD COLUMN confidence REAL DEFAULT 0.5")
    conn.execute(
        "UPDATE learning_entry SET confidence = 0.5 WHERE confidence IS NULL"
    )

    if not _table_has_column(conn, "session", "session_summary"):
        conn.execute("ALTER TABLE session ADD COLUMN session_summary TEXT DEFAULT ''")
    conn.execute(
        "UPDATE session SET session_summary = '' WHERE session_summary IS NULL"
    )
    conn.commit()


def _migrate_add_tier_model_fields(conn: sqlite3.Connection) -> None:
    """Add tier-model assignment columns to ``session`` when missing (v9)."""
    logger.info("Applying DB migration: add session tier model fields")
    if not _table_has_column(conn, "session", "depth_mode"):
        conn.execute("ALTER TABLE session ADD COLUMN depth_mode TEXT DEFAULT 'deep'")
    if not _table_has_column(conn, "session", "frontier_model"):
        conn.execute("ALTER TABLE session ADD COLUMN frontier_model TEXT DEFAULT ''")
    if not _table_has_column(conn, "session", "checker_model"):
        conn.execute("ALTER TABLE session ADD COLUMN checker_model TEXT DEFAULT ''")

    conn.execute(
        "UPDATE session SET depth_mode = 'deep' WHERE depth_mode IS NULL OR depth_mode = ''"
    )
    conn.execute(
        "UPDATE session SET checker_model = model "
        "WHERE checker_model IS NULL OR checker_model = ''"
    )
    conn.execute(
        "UPDATE session "
        "SET frontier_model = COALESCE(NULLIF(discussion_model, ''), model) "
        "WHERE frontier_model IS NULL OR frontier_model = ''"
    )
    conn.commit()


def _migrate_add_scene_projection(conn: sqlite3.Connection) -> None:
    """Add ``scene_projection`` table when missing (v10)."""
    logger.info("Applying DB migration: add scene_projection table")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scene_projection (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               scene_path TEXT NOT NULL UNIQUE,
               scene_id TEXT,
               file_hash TEXT NOT NULL,
               meta_json TEXT NOT NULL DEFAULT '{}',
               last_refreshed_at TEXT NOT NULL
           )"""
    )
    conn.commit()


def _migrate_add_index_projection(conn: sqlite3.Connection) -> None:
    """Add ``index_projection`` table when missing (v11)."""
    logger.info("Applying DB migration: add index_projection table")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS index_projection (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               index_name TEXT NOT NULL UNIQUE,
               file_hash TEXT NOT NULL,
               entries_json TEXT,
               raw_content_hash TEXT NOT NULL,
               last_refreshed_at TEXT NOT NULL
           )"""
    )
    conn.commit()


def _migrate_add_extracted_knowledge(conn: sqlite3.Connection) -> None:
    """Add extracted-knowledge tables when missing (v12)."""
    logger.info("Applying DB migration: add extracted knowledge tables")

    if not _table_exists(conn, "extracted_scene_metadata"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_scene_metadata (
                   scene_filename TEXT NOT NULL PRIMARY KEY,
                   content_hash TEXT NOT NULL,
                   extracted_at TEXT NOT NULL,
                   location TEXT,
                   pov TEXT,
                   tense TEXT,
                   tense_notes TEXT,
                   cast_present TEXT,
                   objective TEXT,
                   cont_anchors TEXT,
                   extract_status TEXT NOT NULL DEFAULT 'ok',
                   extraction_locked INTEGER NOT NULL DEFAULT 0,
                   locked_at TEXT
               )"""
        )

    if not _table_exists(conn, "extracted_characters"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_characters (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL UNIQUE,
                   aka TEXT,
                   category TEXT,
                   traits TEXT,
                   relationships TEXT,
                   first_seen TEXT,
                   last_updated TEXT NOT NULL
               )"""
        )

    if not _table_exists(conn, "extracted_terms"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_terms (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   term TEXT NOT NULL UNIQUE,
                   category TEXT,
                   definition TEXT,
                   translation TEXT,
                   notes TEXT,
                   first_seen TEXT,
                   last_updated TEXT NOT NULL
               )"""
        )

    if not _table_exists(conn, "extracted_threads"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_threads (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   thread_id TEXT NOT NULL UNIQUE,
                   question TEXT,
                   status TEXT,
                   opened_in TEXT,
                   last_advanced TEXT,
                   resolved_in TEXT,
                   notes TEXT,
                   last_updated TEXT NOT NULL
               )"""
        )

    if not _table_exists(conn, "extracted_thread_events"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_thread_events (
                   thread_id TEXT NOT NULL,
                   scene_filename TEXT NOT NULL,
                   event_type TEXT NOT NULL,
                   notes TEXT,
                   PRIMARY KEY (thread_id, scene_filename)
               )"""
        )

    if not _table_exists(conn, "extracted_timeline"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_timeline (
                   scene_filename TEXT NOT NULL PRIMARY KEY,
                   summary TEXT NOT NULL,
                   chrono_hint TEXT,
                   last_updated TEXT NOT NULL
               )"""
        )

    if not _table_exists(conn, "knowledge_overrides"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS knowledge_overrides (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   category TEXT NOT NULL,
                   entity_key TEXT NOT NULL,
                   field_name TEXT NOT NULL,
                   override_value TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   UNIQUE(category, entity_key, field_name)
               )"""
        )

    conn.commit()


def _migrate_add_entity_locking(conn: sqlite3.Connection) -> None:
    """Add ``entity_locked`` and ``locked_at`` columns to entity tables (v14)."""
    logger.info("Applying DB migration: add entity_locked columns")
    for table in ("extracted_characters", "extracted_terms", "extracted_threads", "extracted_timeline"):
        if not _table_has_column(conn, table, "entity_locked"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN entity_locked INTEGER NOT NULL DEFAULT 0")
        if not _table_has_column(conn, table, "locked_at"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN locked_at TEXT")
    conn.commit()


def _migrate_add_source_tables(conn: sqlite3.Connection) -> None:
    """Add character/term provenance source junction tables when missing (v15)."""
    logger.info("Applying DB migration: add extracted source junction tables")
    if not _table_exists(conn, "extracted_character_sources"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_character_sources (
                   name TEXT NOT NULL,
                   scene_filename TEXT NOT NULL,
                   PRIMARY KEY (name, scene_filename)
               )"""
        )
    if not _table_exists(conn, "extracted_term_sources"):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extracted_term_sources (
                   term TEXT NOT NULL,
                   scene_filename TEXT NOT NULL,
                   PRIMARY KEY (term, scene_filename)
               )"""
        )
    conn.commit()


def _migrate_add_knowledge_review_flags(conn: sqlite3.Connection) -> None:
    """Add ``knowledge_review_flags`` table when missing (v16)."""
    logger.info("Applying DB migration: add knowledge_review_flags table")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_review_flags (
               category    TEXT NOT NULL,
               entity_key  TEXT NOT NULL,
               reason      TEXT NOT NULL DEFAULT '',
               flagged_at  TEXT NOT NULL,
               PRIMARY KEY (category, entity_key)
           )"""
    )
    conn.commit()


def _migrate_add_knowledge_staleness_cache(conn: sqlite3.Connection) -> None:
    """Add ``knowledge_staleness_cache`` table when missing (v17)."""
    logger.info("Applying DB migration: add knowledge_staleness_cache table")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_staleness_cache (
               category    TEXT NOT NULL,
               entity_key  TEXT NOT NULL,
               source_path TEXT NOT NULL DEFAULT '',
               cached_at   TEXT NOT NULL,
               PRIMARY KEY (category, entity_key)
           )"""
    )
    conn.commit()


def _migrate_relativize_paths(conn: sqlite3.Connection, project_path: Path) -> None:
    """Rewrite absolute stored paths to project-relative POSIX strings (v13).

    Idempotent: paths already relative (or outside the project root) are left
    unchanged.  Runs only on writable connections obtained via
    ``get_connection()``; passive connections skip this entirely.
    """
    from lit_platform.persistence.path_utils import to_relative  # local import avoids circularity

    root = Path(project_path).resolve()

    def _rel(val: str | None) -> str:
        if not val:
            return val or ""
        return to_relative(root, val)

    def _rel_json_array(raw: str | None) -> str:
        """Relativize each element of a JSON array string."""
        if not raw:
            return raw or "[]"
        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
        if not isinstance(items, list):
            return raw
        return json.dumps([_rel(item) if isinstance(item, str) else item for item in items])

    logger.info("Applying DB migration v13: relativize stored paths")

    changed = False

    # --- session.scene_path (JSON-encoded list) and session.index_changed_files ---
    sessions = conn.execute("SELECT id, scene_path, index_changed_files FROM session").fetchall()
    for row in sessions:
        new_scene = _rel_json_array(row["scene_path"])
        new_changed = _rel_json_array(row["index_changed_files"])
        if new_scene != row["scene_path"] or new_changed != row["index_changed_files"]:
            conn.execute(
                "UPDATE session SET scene_path = ?, index_changed_files = ? WHERE id = ?",
                (new_scene, new_changed, row["id"]),
            )
            changed = True

    # --- finding.scene_path (plain string) ---
    findings = conn.execute("SELECT id, scene_path FROM finding WHERE scene_path IS NOT NULL").fetchall()
    for row in findings:
        new_path = _rel(row["scene_path"])
        if new_path != row["scene_path"]:
            conn.execute(
                "UPDATE finding SET scene_path = ? WHERE id = ?",
                (new_path, row["id"]),
            )
            changed = True

    # --- scene_projection.scene_path (unique key, plain string) ---
    # Use a temp-rename approach to avoid unique-constraint conflicts mid-update
    projections = conn.execute("SELECT id, scene_path FROM scene_projection").fetchall()
    for row in projections:
        new_path = _rel(row["scene_path"])
        if new_path != row["scene_path"]:
            conn.execute(
                "UPDATE scene_projection SET scene_path = ? WHERE id = ?",
                (new_path, row["id"]),
            )
            changed = True

    if changed:
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
    depth_mode TEXT DEFAULT 'deep',
    frontier_model TEXT DEFAULT '',
    checker_model TEXT DEFAULT '',
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
    outcome_reason TEXT DEFAULT '',
    origin TEXT DEFAULT 'legacy'
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
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_learning_entry_category ON learning_entry(category);

CREATE TABLE IF NOT EXISTS scene_projection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_path TEXT NOT NULL UNIQUE,
    scene_id TEXT,
    file_hash TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    last_refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_projection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_name TEXT NOT NULL UNIQUE,
    file_hash TEXT NOT NULL,
    entries_json TEXT,
    raw_content_hash TEXT NOT NULL,
    last_refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extracted_scene_metadata (
    scene_filename TEXT NOT NULL PRIMARY KEY,
    content_hash TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    location TEXT,
    pov TEXT,
    tense TEXT,
    tense_notes TEXT,
    cast_present TEXT,
    objective TEXT,
    cont_anchors TEXT,
    extract_status TEXT NOT NULL DEFAULT 'ok',
    extraction_locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    aka TEXT,
    category TEXT,
    traits TEXT,
    relationships TEXT,
    first_seen TEXT,
    last_updated TEXT NOT NULL,
    entity_locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    category TEXT,
    definition TEXT,
    translation TEXT,
    notes TEXT,
    first_seen TEXT,
    last_updated TEXT NOT NULL,
    entity_locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,
    question TEXT,
    status TEXT,
    opened_in TEXT,
    last_advanced TEXT,
    resolved_in TEXT,
    notes TEXT,
    last_updated TEXT NOT NULL,
    entity_locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_thread_events (
    thread_id TEXT NOT NULL,
    scene_filename TEXT NOT NULL,
    event_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (thread_id, scene_filename)
);

CREATE TABLE IF NOT EXISTS extracted_timeline (
    scene_filename TEXT NOT NULL PRIMARY KEY,
    summary TEXT NOT NULL,
    chrono_hint TEXT,
    last_updated TEXT NOT NULL,
    entity_locked INTEGER NOT NULL DEFAULT 0,
    locked_at TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    override_value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(category, entity_key, field_name)
);

CREATE TABLE IF NOT EXISTS extracted_character_sources (
    name TEXT NOT NULL,
    scene_filename TEXT NOT NULL,
    PRIMARY KEY (name, scene_filename)
);

CREATE TABLE IF NOT EXISTS extracted_term_sources (
    term TEXT NOT NULL,
    scene_filename TEXT NOT NULL,
    PRIMARY KEY (term, scene_filename)
);

CREATE TABLE IF NOT EXISTS knowledge_review_flags (
    category    TEXT NOT NULL,
    entity_key  TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    flagged_at  TEXT NOT NULL,
    PRIMARY KEY (category, entity_key)
);

CREATE TABLE IF NOT EXISTS knowledge_staleness_cache (
    category    TEXT NOT NULL,
    entity_key  TEXT NOT NULL,
    source_path TEXT NOT NULL DEFAULT '',
    cached_at   TEXT NOT NULL,
    PRIMARY KEY (category, entity_key)
);
"""


__all__ = [
    "SCHEMA_VERSION",
    "get_db_path",
    "get_connection",
    "get_passive_connection",
    "init_db",
]
