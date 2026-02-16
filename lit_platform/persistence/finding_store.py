"""Platform-owned finding store."""

import json
import sqlite3
from typing import Optional


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
        """Update specific fields of a finding."""
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


__all__ = ["FindingStore"]
