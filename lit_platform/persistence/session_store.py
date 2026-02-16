"""Platform-owned session store."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


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
        """Recalculate and update finding counts for a session."""
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
        """Re-open a completed session back to active status."""
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
        """Validate that a saved session matches the current scene."""
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
        if "stale" in d:
            d["stale"] = bool(d["stale"])
        return d


__all__ = ["SessionStore"]
