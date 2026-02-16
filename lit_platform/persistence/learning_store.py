"""Platform-owned learning store."""

import sqlite3
from datetime import datetime

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
        """Ensure a learning record exists, creating one if needed."""
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
        """Load learning data as a dict with entries grouped by category."""
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
        """Persist a ``LearningData`` object to the database."""
        learning_id = LearningStore.ensure_exists(
            conn, learning_data.project_name
        )
        now = datetime.now().isoformat()

        conn.execute(
            "UPDATE learning SET project_name = ?, review_count = ?, updated_at = ? WHERE id = ?",
            (learning_data.project_name, learning_data.review_count, now, learning_id),
        )

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
        """Add an ambiguity entry (intentional or accidental)."""
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


__all__ = [
    "LearningStore",
    "CATEGORY_PREFERENCE",
    "CATEGORY_BLIND_SPOT",
    "CATEGORY_RESOLUTION",
    "CATEGORY_AMBIGUITY_INTENTIONAL",
    "CATEGORY_AMBIGUITY_ACCIDENTAL",
    "ALL_CATEGORIES",
]
