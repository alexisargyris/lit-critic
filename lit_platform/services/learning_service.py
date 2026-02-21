"""Platform-owned learning service."""

from datetime import datetime
from pathlib import Path

from lit_platform.persistence import LearningStore, get_connection
from lit_platform.runtime.models import LearningData


def load_learning(project_path: Path) -> LearningData:
    """Load learning data from SQLite, with legacy LEARNING.md one-time import."""
    conn = get_connection(project_path)
    try:
        data = LearningStore.load(conn)

        if data.get("id") is not None:
            return _dict_to_learning_data(data)

        learning = _load_learning_from_markdown(project_path)
        if learning.project_name != "Unknown" or learning.review_count > 0 or learning.preferences:
            LearningStore.save_from_learning_data(conn, learning)

        return learning
    finally:
        conn.close()


def load_learning_from_db(conn) -> LearningData:
    """Load learning data from an already-open DB connection."""
    data = LearningStore.load(conn)
    return _dict_to_learning_data(data)


def _dict_to_learning_data(data: dict) -> LearningData:
    """Convert LearningStore dict payload to ``LearningData``."""
    learning = LearningData(
        project_name=data.get("project_name", "Unknown"),
        review_count=data.get("review_count", 0),
    )
    for entry in data.get("preferences", []):
        learning.preferences.append({
            "id": entry.get("id"),
            "description": entry.get("description", str(entry)),
        })
    for entry in data.get("blind_spots", []):
        learning.blind_spots.append({
            "id": entry.get("id"),
            "description": entry.get("description", str(entry)),
        })
    for entry in data.get("resolutions", []):
        learning.resolutions.append({
            "id": entry.get("id"),
            "description": entry.get("description", str(entry)),
        })
    for entry in data.get("ambiguity_intentional", []):
        learning.ambiguity_intentional.append({
            "id": entry.get("id"),
            "description": entry.get("description", str(entry)),
        })
    for entry in data.get("ambiguity_accidental", []):
        learning.ambiguity_accidental.append({
            "id": entry.get("id"),
            "description": entry.get("description", str(entry)),
        })
    return learning


def _load_learning_from_markdown(project_path: Path) -> LearningData:
    """Parse existing LEARNING.md (legacy format) for one-time import."""
    learning = LearningData()
    filepath = project_path / "LEARNING.md"

    if not filepath.exists():
        return learning

    content = filepath.read_text(encoding="utf-8")

    current_section = None
    current_subsection = None

    for line in content.split("\n"):
        line = line.strip()

        if line.startswith("PROJECT:"):
            learning.project_name = line.split(":", 1)[1].strip()
        elif line.startswith("REVIEW_COUNT:"):
            try:
                learning.review_count = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line == "## Preferences":
            current_section = "preferences"
        elif line == "## Blind Spots":
            current_section = "blind_spots"
        elif line == "## Resolutions":
            current_section = "resolutions"
        elif line == "## Ambiguity Patterns":
            current_section = "ambiguity"
        elif line == "### Intentional":
            current_subsection = "intentional"
        elif line == "### Accidental":
            current_subsection = "accidental"
        elif line.startswith("- ") and current_section:
            entry = {"description": line[2:]}
            if current_section == "preferences":
                learning.preferences.append(entry)
            elif current_section == "blind_spots":
                learning.blind_spots.append(entry)
            elif current_section == "resolutions":
                learning.resolutions.append(entry)
            elif current_section == "ambiguity":
                if current_subsection == "intentional":
                    learning.ambiguity_intentional.append(entry)
                elif current_subsection == "accidental":
                    learning.ambiguity_accidental.append(entry)

    return learning


def persist_learning(learning: LearningData, project_path: Path) -> None:
    """Save learning data to the project's SQLite database."""
    conn = get_connection(project_path)
    try:
        LearningStore.save_from_learning_data(conn, learning)
    finally:
        conn.close()


def persist_learning_with_conn(learning: LearningData, conn) -> None:
    """Save learning data using an already-open DB connection."""
    LearningStore.save_from_learning_data(conn, learning)


def commit_pending_learning_entries(learning: LearningData, conn) -> None:
    """Immediately write any unprocessed session learning events to ``learning_entry``.

    This is the hot path called after every user action (reject, ambiguity,
    discussion preference).  It drains the three session lists, writes each
    new entry to SQLite via ``LearningStore``, updates the in-memory
    long-term lists, and clears the processed items so subsequent calls are
    idempotent.

    ``review_count`` is intentionally *not* touched here — it is incremented
    once at session completion via ``LearningStore.increment_review_count()``.
    """
    if conn is None:
        return

    # Process rejections → preferences
    unprocessed_rejections = []
    for rejection in learning.session_rejections:
        if rejection.get("preference_rule"):
            desc = f"[{rejection['lens']}] {rejection['preference_rule']}"
        else:
            reason = rejection.get("reason", "no reason given")
            desc = f"[{rejection['lens']}] {rejection['pattern']} — Author says: \"{reason}\""
        if not any(desc in p.get("description", "") for p in learning.preferences):
            entry_id = LearningStore.add_preference(conn, desc)
            learning.preferences.append({"id": entry_id, "description": desc})
        # Either way mark as processed — duplicate check already ran
    learning.session_rejections = unprocessed_rejections  # drained (always empty)

    # Process ambiguity answers → ambiguity_intentional / ambiguity_accidental
    unprocessed_ambiguity = []
    for answer in learning.session_ambiguity_answers:
        desc = f"{answer['location']}: {answer['description']}"
        if answer["intentional"]:
            if not any(desc in a.get("description", "") for a in learning.ambiguity_intentional):
                entry_id = LearningStore.add_ambiguity(conn, desc, intentional=True)
                learning.ambiguity_intentional.append({"id": entry_id, "description": desc})
        else:
            if not any(desc in a.get("description", "") for a in learning.ambiguity_accidental):
                entry_id = LearningStore.add_ambiguity(conn, desc, intentional=False)
                learning.ambiguity_accidental.append({"id": entry_id, "description": desc})
    learning.session_ambiguity_answers = unprocessed_ambiguity  # drained (always empty)

    # session_acceptances are not yet mapped to long-term entries; clear them too
    learning.session_acceptances = []


def update_learning_from_session(learning: LearningData) -> None:
    """Process any remaining session data into long-term learning entries.

    .. deprecated::
        Prefer ``commit_pending_learning_entries()`` which writes to SQLite
        immediately after each user action.  This function is retained for
        use in offline / test scenarios where there is no open DB connection.
        It no longer increments ``review_count`` — callers should use
        ``LearningStore.increment_review_count()`` at session completion.
    """
    for rejection in learning.session_rejections:
        if rejection.get("preference_rule"):
            desc = f"[{rejection['lens']}] {rejection['preference_rule']}"
        else:
            reason = rejection.get("reason", "no reason given")
            desc = f"[{rejection['lens']}] {rejection['pattern']} — Author says: \"{reason}\""
        if not any(desc in p.get("description", "") for p in learning.preferences):
            learning.preferences.append({"description": desc})

    for answer in learning.session_ambiguity_answers:
        desc = f"{answer['location']}: {answer['description']}"
        if answer["intentional"]:
            if not any(desc in a.get("description", "") for a in learning.ambiguity_intentional):
                learning.ambiguity_intentional.append({"description": desc})
        else:
            if not any(desc in a.get("description", "") for a in learning.ambiguity_accidental):
                learning.ambiguity_accidental.append({"description": desc})

    learning.session_rejections = []
    learning.session_acceptances = []
    learning.session_ambiguity_answers = []


def generate_learning_markdown(learning: LearningData) -> str:
    """Generate LEARNING.md content from learning data."""
    lines = [
        "# Learning",
        "",
        f"PROJECT: {learning.project_name}",
        f"LAST_UPDATED: {datetime.now().strftime('%Y-%m-%d')}",
        f"REVIEW_COUNT: {learning.review_count}",
        "",
        "## Preferences",
        "",
    ]

    if learning.preferences:
        for pref in learning.preferences:
            lines.append(f"- {pref.get('description', pref)}")
    else:
        lines.append("[none yet]")

    lines.extend(["", "## Blind Spots", ""])
    if learning.blind_spots:
        for bs in learning.blind_spots:
            lines.append(f"- {bs.get('description', bs)}")
    else:
        lines.append("[none yet]")

    lines.extend(["", "## Resolutions", ""])
    if learning.resolutions:
        for res in learning.resolutions:
            lines.append(f"- {res.get('description', res)}")
    else:
        lines.append("[none yet]")

    lines.extend(["", "## Ambiguity Patterns", "", "### Intentional", ""])
    if learning.ambiguity_intentional:
        for amb in learning.ambiguity_intentional:
            lines.append(f"- {amb.get('description', amb)}")
    else:
        lines.append("[none yet]")

    lines.extend(["", "### Accidental", ""])
    if learning.ambiguity_accidental:
        for amb in learning.ambiguity_accidental:
            lines.append(f"- {amb.get('description', amb)}")
    else:
        lines.append("[none yet]")

    return "\n".join(lines)


def export_learning_markdown(project_path: Path) -> Path:
    """Export learning data from database to LEARNING.md."""
    conn = get_connection(project_path)
    try:
        markdown = LearningStore.export_markdown(conn)
    finally:
        conn.close()

    filepath = project_path / "LEARNING.md"
    filepath.write_text(markdown, encoding="utf-8")
    return filepath


def save_learning_to_file(learning: LearningData, project_path: Path) -> Path:
    """Update/persist learning and write LEARNING.md."""
    update_learning_from_session(learning)
    persist_learning(learning, project_path)

    markdown = generate_learning_markdown(learning)
    filepath = project_path / "LEARNING.md"
    filepath.write_text(markdown, encoding="utf-8")
    return filepath


def reset_learning(project_path: Path) -> None:
    """Reset persisted learning data for a project."""
    conn = get_connection(project_path)
    try:
        LearningStore.reset(conn)
    finally:
        conn.close()
