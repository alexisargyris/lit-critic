import sqlite3
import sys
from pathlib import Path

from lit_platform.persistence.database import _migrate_relativize_paths, init_db
from lit_platform.persistence.index_projection_store import IndexProjectionStore
from lit_platform.persistence.scene_projection_store import SceneProjectionStore
from lit_platform.persistence.session_store import SessionStore


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_scene_projection_store_upsert_load_stale_and_delete():
    conn = _conn()
    try:
        SceneProjectionStore.upsert(
            conn,
            scene_path="text/ch1.txt",
            scene_id="SCN-001",
            file_hash="hash-v1",
            meta_json={"title": "Chapter 1"},
        )

        row = SceneProjectionStore.load_by_path(conn, "text/ch1.txt")
        assert row is not None
        assert row["scene_id"] == "SCN-001"
        assert row["file_hash"] == "hash-v1"
        assert row["meta_json"]["title"] == "Chapter 1"

        all_rows = SceneProjectionStore.load_all(conn)
        assert [r["scene_path"] for r in all_rows] == ["text/ch1.txt"]

        assert SceneProjectionStore.is_stale(conn, "text/ch1.txt", "hash-v1") is False
        assert SceneProjectionStore.is_stale(conn, "text/ch1.txt", "hash-v2") is True
        assert SceneProjectionStore.is_stale(conn, "text/missing.txt", "hash-any") is True

        SceneProjectionStore.upsert(
            conn,
            scene_path="text/ch1.txt",
            scene_id="SCN-001B",
            file_hash="hash-v2",
            meta_json={"title": "Chapter 1 revised"},
        )

        updated = SceneProjectionStore.load_by_path(conn, "text/ch1.txt")
        assert updated is not None
        assert updated["scene_id"] == "SCN-001B"
        assert updated["file_hash"] == "hash-v2"
        assert updated["meta_json"]["title"] == "Chapter 1 revised"

        SceneProjectionStore.delete_by_path(conn, "text/ch1.txt")
        assert SceneProjectionStore.load_by_path(conn, "text/ch1.txt") is None
    finally:
        conn.close()


def test_index_projection_store_upsert_load_and_stale_detection():
    conn = _conn()
    try:
        IndexProjectionStore.upsert(
            conn,
            index_name="CAST.md",
            file_hash="index-hash-v1",
            entries_json=[{"name": "Alice", "role": "lead"}],
        )

        row = IndexProjectionStore.load_by_name(conn, "CAST.md")
        assert row is not None
        assert row["index_name"] == "CAST.md"
        assert row["file_hash"] == "index-hash-v1"
        assert isinstance(row["entries_json"], list)
        assert row["entries_json"][0]["name"] == "Alice"
        assert row["raw_content_hash"] == "index-hash-v1"

        all_rows = IndexProjectionStore.load_all(conn)
        assert [r["index_name"] for r in all_rows] == ["CAST.md"]

        assert IndexProjectionStore.is_stale(conn, "CAST.md", "index-hash-v1") is False
        assert IndexProjectionStore.is_stale(conn, "CAST.md", "index-hash-v2") is True
        assert IndexProjectionStore.is_stale(conn, "THREADS.md", "index-hash") is True

        IndexProjectionStore.upsert(
            conn,
            index_name="STYLE.md",
            file_hash="style-hash-v1",
            entries_json=None,
            raw_content_hash="style-raw-hash-v1",
        )

        style_row = IndexProjectionStore.load_by_name(conn, "STYLE.md")
        assert style_row is not None
        assert style_row["entries_json"] is None
        assert style_row["raw_content_hash"] == "style-raw-hash-v1"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Portability tests (Task 5) — session paths survive migration across roots
# ---------------------------------------------------------------------------

def _root() -> Path:
    """Return a stable absolute project root for the current platform."""
    if sys.platform == "win32":
        return Path("C:/Projects/mynovel")
    return Path("/home/alice/novel")


def _abs(rel: str) -> str:
    return str(_root() / rel)


def test_session_portability_scene_paths_absolutized_after_migration():
    """Paths written as absolute on machine A should be readable as absolute on machine B."""
    conn = _conn()
    try:
        # Machine A: create session with absolute paths
        abs_scene = _abs("scenes/ch01.txt")
        abs_changed = _abs("indexes/CAST.md")
        SessionStore.create(
            conn,
            scene_path=abs_scene,
            scene_hash="sha-abc",
            model="gpt-4",
            index_changed_files=[abs_changed],
        )

        # Simulate v13 migration: relativize using machine A's root
        _migrate_relativize_paths(conn, _root())

        # Machine B: different root, but relative paths reattach correctly
        machine_b_root = Path("C:/Users/bob/projects/mynovel") if sys.platform == "win32" else Path("/home/bob/novel")

        session = SessionStore.load_active(conn, project_path=machine_b_root)
        assert session is not None

        # scene_paths should now be absolute under machine B's root
        expected_scene = str((machine_b_root / "scenes/ch01.txt").resolve())
        assert session["scene_paths"] == [expected_scene]
        assert session["scene_path"] == expected_scene

        expected_changed = str((machine_b_root / "indexes/CAST.md").resolve())
        assert session["index_changed_files"] == [expected_changed]
    finally:
        conn.close()


def test_session_portability_validate_succeeds_after_migration():
    """validate() must succeed when scene_path was stored relative and re-read with project_path."""
    conn = _conn()
    try:
        abs_scene = _abs("scenes/ch01.txt")
        SessionStore.create(
            conn,
            scene_path=abs_scene,
            scene_hash="sha-xyz",
            model="gpt-4",
        )

        # Run migration
        _migrate_relativize_paths(conn, _root())

        # Load back using the same root (simulating same-machine open after migration)
        session = SessionStore.load_active(conn, project_path=_root())
        assert session is not None

        ok, msg = SessionStore.validate(
            session, "sha-xyz", abs_scene, project_path=_root()
        )
        assert ok, f"validate() failed unexpectedly: {msg}"
    finally:
        conn.close()


def test_session_portability_already_relative_paths_not_doubled():
    """Paths stored relative should not be double-relativized on second migration run."""
    conn = _conn()
    try:
        abs_scene = _abs("scenes/ch02.txt")
        SessionStore.create(
            conn,
            scene_path=abs_scene,
            scene_hash="sha-def",
            model="gpt-4",
        )

        # Run migration twice (idempotency check)
        _migrate_relativize_paths(conn, _root())
        _migrate_relativize_paths(conn, _root())

        session = SessionStore.load_active(conn, project_path=_root())
        assert session is not None
        expected = str((_root() / "scenes/ch02.txt").resolve())
        assert session["scene_paths"] == [expected]
    finally:
        conn.close()
