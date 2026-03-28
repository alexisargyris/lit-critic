"""Platform-owned session workflow service."""

import hashlib
import json
from pathlib import Path
from typing import Optional

from lit_platform.persistence import FindingStore, SessionStore
from lit_platform.persistence.database import get_connection, get_passive_connection
from lit_platform.persistence.path_utils import to_absolute, to_relative
from lit_platform.runtime.config import CONTEXT_FILES
from lit_platform.runtime.prompts import get_session_summary_prompt
from lit_platform.session_state_machine import (
    all_findings_considered as platform_all_findings_considered,
    first_unresolved_index,
    is_terminal_status,
    learning_session_payload,
)
from lit_platform.runtime.models import Finding, SessionState
from lit_platform.runtime.utils import apply_scene_change, concatenate_scenes
from lit_platform.services.index_service import get_finding_index_context
from lit_platform.services.learning_service import generate_learning_markdown, load_learning_from_db


def compute_scene_hash(scene_content: str) -> str:
    """Compute a hash of the scene content for change detection."""
    return hashlib.sha256(scene_content.encode("utf-8")).hexdigest()[:16]


def compute_index_context_hash(indexes: dict[str, str]) -> str:
    """Compute a stable hash for context-bearing index inputs."""
    normalized_payload = {
        name: indexes.get(name, "")
        for name in CONTEXT_FILES
    }
    payload = json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_current_index_context(state: SessionState) -> dict[str, str]:
    """Load latest index context from disk (+ synthetic LEARNING.md from DB)."""
    current: dict[str, str] = {}
    for filename in CONTEXT_FILES:
        if filename == "LEARNING.md":
            continue
        path = state.project_path / filename
        try:
            current[filename] = path.read_text(encoding="utf-8") if path.exists() else ""
        except OSError:
            current[filename] = ""

    if state.db_conn:
        learning = load_learning_from_db(state.db_conn)
    else:
        learning = state.learning
    current["LEARNING.md"] = generate_learning_markdown(learning)

    return current


def detect_index_context_changes(state: SessionState) -> Optional[dict]:
    """Detect index context drift and apply prompt-once stale semantics."""
    current_indexes = _load_current_index_context(state)
    current_hash = compute_index_context_hash(current_indexes)

    if not state.index_context_hash:
        state.index_context_hash = current_hash
        state.index_context_stale = False
        state.index_rerun_prompted = False
        state.index_changed_files = []
        state.indexes.update(current_indexes)
        if state.db_conn and state.session_id:
            SessionStore.update_index_context(
                state.db_conn,
                state.session_id,
                index_context_hash=state.index_context_hash,
                index_context_stale=False,
                index_rerun_prompted=False,
                index_changed_files=[],
                project_path=state.project_path,
            )
        return None

    if current_hash == state.index_context_hash:
        return None

    baseline_indexes = {name: state.indexes.get(name, "") for name in CONTEXT_FILES}
    changed_files = [
        filename for filename in CONTEXT_FILES
        if filename != "LEARNING.md"
        and current_indexes.get(filename, "") != baseline_indexes.get(filename, "")
    ]

    # LEARNING.md is session-to-session memory and should not trigger stale/rerun
    # prompts for the current review session. If only LEARNING changed, silently
    # re-baseline the hash and keep stale flags cleared.
    if not changed_files:
        state.index_context_hash = current_hash
        state.index_context_stale = False
        state.index_rerun_prompted = False
        state.index_changed_files = []
        state.indexes.update(current_indexes)
        if state.db_conn and state.session_id:
            SessionStore.update_index_context(
                state.db_conn,
                state.session_id,
                index_context_hash=state.index_context_hash,
                index_context_stale=False,
                index_rerun_prompted=False,
                index_changed_files=[],
                project_path=state.project_path,
            )
        return None

    should_prompt = not state.index_rerun_prompted
    state.index_context_stale = True
    state.index_changed_files = changed_files
    if should_prompt:
        state.index_rerun_prompted = True

    if state.db_conn and state.session_id:
        SessionStore.mark_index_context_stale(
            state.db_conn,
            state.session_id,
            changed_files=changed_files,
            prompted=state.index_rerun_prompted,
            project_path=state.project_path,
        )

    return {
        "changed": True,
        "stale": True,
        "changed_files": changed_files,
        "prompt": should_prompt,
    }


def is_terminal_finding_status(status: str) -> bool:
    """Return True when a finding status counts as fully considered."""
    return is_terminal_status(status)


def all_findings_considered(findings: list[Finding]) -> bool:
    """Return True when every finding is in a terminal status."""
    return platform_all_findings_considered(findings)


def first_unresolved_finding_index(findings: list[Finding]) -> Optional[int]:
    """Return the index of the first non-terminal finding, or None."""
    return first_unresolved_index(findings)


def create_session(state: SessionState, glossary_issues: list[str] | None = None) -> int:
    """Create a new active session in the database and persist all findings."""
    conn = get_connection(state.project_path)
    state.db_conn = conn

    scene_hash = compute_scene_hash(state.scene_content)
    if not state.index_context_hash:
        baseline_indexes = _load_current_index_context(state)
        state.indexes.update(baseline_indexes)
        state.index_context_hash = compute_index_context_hash(state.indexes)
    session_id = SessionStore.create(
        conn,
        scene_path=state.scene_path,
        scene_hash=scene_hash,
        model=state.model,
        depth_mode=getattr(state, "depth_mode", None),
        frontier_model=getattr(state, "effective_frontier_model", None),
        checker_model=getattr(state, "effective_checker_model", None),
        scene_paths=state.scene_paths or [state.scene_path],
        glossary_issues=glossary_issues or state.glossary_issues,
        discussion_model=state.discussion_model,
        index_context_hash=state.index_context_hash,
        index_context_stale=state.index_context_stale,
        index_rerun_prompted=state.index_rerun_prompted,
        index_changed_files=state.index_changed_files,
        project_path=state.project_path,
    )
    state.session_id = session_id

    findings_dicts = [f.to_dict(include_state=True) for f in state.findings]
    FindingStore.save_all(conn, session_id, findings_dicts, project_path=state.project_path)

    conn.execute(
        "UPDATE session SET total_findings = ? WHERE id = ?",
        (len(findings_dicts), session_id),
    )
    conn.commit()

    _persist_learning_session(state)
    return session_id


def _get_session_read_connection(
    project_path: Path,
    *,
    passive: bool,
):
    """Return the appropriate connection for session read operations."""
    if passive:
        return get_passive_connection(project_path)
    return get_connection(project_path)


def _build_active_session_payload(
    conn,
    *,
    refresh_counts: bool,
    project_path: Path | None = None,
) -> Optional[dict]:
    """Load active session data and findings into a serializable payload."""
    session_data = SessionStore.load_active(conn, project_path=project_path)
    if session_data is None:
        return None

    findings = FindingStore.load_all(conn, session_data["id"], project_path=project_path)
    if refresh_counts:
        SessionStore.update_counts(conn, session_data["id"])
        session_data = SessionStore.get(conn, session_data["id"], project_path=project_path)

    return {
        "session_id": session_data["id"],
        "scene_path": session_data.get("scene_path", ""),
        "scene_paths": session_data.get("scene_paths", []),
        "scene_hash": session_data.get("scene_hash", ""),
        "model": session_data.get("model", ""),
        "discussion_model": session_data.get("discussion_model"),
        "depth_mode": session_data.get("depth_mode"),
        "frontier_model": session_data.get("frontier_model"),
        "checker_model": session_data.get("checker_model"),
        "current_index": session_data.get("current_index", 0),
        "glossary_issues": session_data.get("glossary_issues", []),
        "discussion_history": session_data.get("discussion_history", []),
        "learning_session": session_data.get("learning_session", {}),
        "index_context_hash": session_data.get("index_context_hash", ""),
        "index_context_stale": session_data.get("index_context_stale", False),
        "index_rerun_prompted": session_data.get("index_rerun_prompted", False),
        "index_changed_files": session_data.get("index_changed_files", []),
        "findings": findings,
        "created_at": session_data.get("created_at", ""),
        "accepted_count": session_data.get("accepted_count", 0),
        "rejected_count": session_data.get("rejected_count", 0),
        "withdrawn_count": session_data.get("withdrawn_count", 0),
    }


def check_active_session(project_path: Path, passive: bool = False) -> Optional[dict]:
    """Check if an active session exists for the project."""
    conn = _get_session_read_connection(project_path, passive=passive)
    if conn is None:
        return {"exists": False}

    try:
        session_data = SessionStore.load_active(conn, project_path=project_path)
        if session_data is None:
            return {"exists": False}

        findings = FindingStore.load_all(conn, session_data["id"], project_path=project_path)
        return {
            "exists": True,
            "session_id": session_data["id"],
            "scene_path": session_data.get("scene_path", ""),
            "scene_paths": session_data.get("scene_paths", []),
            "created_at": session_data.get("created_at", ""),
            "current_index": session_data.get("current_index", 0),
            "total_findings": len(findings),
            "model": session_data.get("model", ""),
            "discussion_model": session_data.get("discussion_model"),
        }
    finally:
        conn.close()


def load_active_session(project_path: Path, passive: bool = False) -> Optional[dict]:
    """Load the full active session data including findings."""
    conn = _get_session_read_connection(project_path, passive=passive)
    if conn is None:
        return None

    if passive:
        try:
            return _build_active_session_payload(conn, refresh_counts=False, project_path=project_path)
        finally:
            conn.close()

    session_payload = _build_active_session_payload(conn, refresh_counts=True, project_path=project_path)
    if session_payload is None:
        conn.close()
        return None

    session_payload["_conn"] = conn
    return session_payload


def _build_session_payload(
    session_data: dict,
    findings: list[dict],
) -> dict:
    """Normalize persisted session data into the session payload shape."""
    return {
        "session_id": session_data["id"],
        "scene_path": session_data.get("scene_path", ""),
        "scene_paths": session_data.get("scene_paths", []),
        "scene_hash": session_data.get("scene_hash", ""),
        "model": session_data.get("model", ""),
        "discussion_model": session_data.get("discussion_model"),
        "depth_mode": session_data.get("depth_mode"),
        "frontier_model": session_data.get("frontier_model"),
        "checker_model": session_data.get("checker_model"),
        "current_index": session_data.get("current_index", 0),
        "glossary_issues": session_data.get("glossary_issues", []),
        "discussion_history": session_data.get("discussion_history", []),
        "learning_session": session_data.get("learning_session", {}),
        "index_context_hash": session_data.get("index_context_hash", ""),
        "index_context_stale": session_data.get("index_context_stale", False),
        "index_rerun_prompted": session_data.get("index_rerun_prompted", False),
        "index_changed_files": session_data.get("index_changed_files", []),
        "findings": findings,
        "created_at": session_data.get("created_at", ""),
        "status": session_data.get("status", "active"),
        "accepted_count": session_data.get("accepted_count", 0),
        "rejected_count": session_data.get("rejected_count", 0),
        "withdrawn_count": session_data.get("withdrawn_count", 0),
    }


def load_session_by_id(
    project_path: Path,
    session_id: int,
    passive: bool = False,
) -> Optional[dict]:
    """Load a specific session by id including findings.

    When ``passive`` is true, reads use the startup-safe query-only connection
    and skip count refreshes that would otherwise dirty the database.
    """
    conn = _get_session_read_connection(project_path, passive=passive)
    if conn is None:
        return None

    session_data = SessionStore.get(conn, session_id, project_path=project_path)
    if session_data is None:
        conn.close()
        return None

    if session_data.get("status") == "active" and not passive:
        SessionStore.update_counts(conn, session_id)
        session_data = SessionStore.get(conn, session_id, project_path=project_path)

    findings = FindingStore.load_all(conn, session_id, project_path=project_path)

    session_payload = _build_session_payload(session_data, findings)
    if passive:
        conn.close()
        return session_payload

    session_payload["_conn"] = conn
    return session_payload


def complete_session(state: SessionState) -> bool:
    """Mark the active session as completed iff all findings are terminal."""
    if not state.db_conn or not state.session_id:
        return False
    if not all_findings_considered(state.findings):
        return False
    SessionStore.complete(state.db_conn, state.session_id)
    return True


async def generate_and_save_session_summary(state: SessionState) -> Optional[str]:
    """Generate and persist a session-end disconfirming meta-observation.

    Uses the discussion model (cheaper/faster) for cost efficiency.
    Should be called after ``complete_session()`` — the summary is
    non-interactive and display-only.  Stored on the session row for later
    retrieval by all clients (CLI, Web, VS Code).

    Returns:
        The generated summary text, or None if generation fails or the
        session has no database connection.
    """
    if not state.db_conn or not state.session_id:
        return None

    learning_markdown = generate_learning_markdown(state.learning)
    prompt = get_session_summary_prompt(
        state.findings,
        state.scene_content,
        learning_markdown=learning_markdown,
    )

    try:
        response = await state.effective_discussion_client.create_message(
            model=state.discussion_model_id,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text = response.text.strip()
    except Exception:
        return None

    SessionStore.update_session_summary(state.db_conn, state.session_id, summary_text)
    return summary_text


def abandon_session(state: SessionState) -> None:
    """Mark the active session as abandoned."""
    if state.db_conn and state.session_id:
        SessionStore.abandon(state.db_conn, state.session_id)


def abandon_active_session(project_path: Path) -> bool:
    """Find and abandon the active session (if any)."""
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.load_active(conn, project_path=project_path)
        if session_data is None:
            return False
        SessionStore.abandon(conn, session_data["id"])
        return True
    finally:
        conn.close()


def complete_active_session(project_path: Path) -> bool:
    """Find and complete the active session (if any)."""
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.load_active(conn, project_path=project_path)
        if session_data is None:
            return False
        findings = FindingStore.load_all(conn, session_data["id"], project_path=project_path)
        if any(not is_terminal_status(f.get("status", "pending")) for f in findings):
            return False
        SessionStore.complete(conn, session_data["id"])
        return True
    finally:
        conn.close()


def _sync_session_completion_state(state: SessionState) -> None:
    """Keep persisted session status aligned with finding terminality."""
    if not state.db_conn or not state.session_id:
        return

    session_row = SessionStore.get(state.db_conn, state.session_id, project_path=state.project_path)
    if not session_row:
        return

    complete_now = all_findings_considered(state.findings)
    status = session_row.get("status")

    if complete_now and status != "completed":
        SessionStore.complete(state.db_conn, state.session_id)
    elif not complete_now and status == "completed":
        SessionStore.reopen(state.db_conn, state.session_id)


def delete_session_by_id(project_path: Path, session_id: int) -> bool:
    """Delete a specific session by id."""
    conn = get_connection(project_path)
    try:
        return SessionStore.delete(conn, session_id)
    finally:
        conn.close()


def list_sessions(project_path: Path, passive: bool = False) -> list[dict]:
    """List all sessions for the project, newest first."""
    conn = _get_session_read_connection(project_path, passive=passive)
    if conn is None:
        return []

    try:
        return SessionStore.list_all(conn, project_path=project_path)
    finally:
        conn.close()


def get_session_detail(
    project_path: Path,
    session_id: int,
    passive: bool = False,
) -> Optional[dict]:
    """Get a session and its findings by id.

    When ``passive`` is true, reads use the startup-safe query-only connection
    and skip count refreshes that would otherwise dirty the database.
    """
    conn = _get_session_read_connection(project_path, passive=passive)
    if conn is None:
        return None

    try:
        session_data = SessionStore.get(conn, session_id, project_path=project_path)
        if session_data is None:
            return None

        if session_data.get("status") == "active" and not passive:
            SessionStore.update_counts(conn, session_id)
            session_data = SessionStore.get(conn, session_id, project_path=project_path)

        findings = FindingStore.load_all(conn, session_id, project_path=project_path)
        session_data["findings"] = findings
        return session_data
    finally:
        conn.close()


def get_rejection_pattern_analytics(
    project_path: Path,
    limit: int = 50,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Aggregate rejected findings by lens/severity for analytics consumers."""
    bounded_limit = max(1, min(int(limit), 500))
    filters = ["f.status = ?"]
    params: list[object] = ["rejected"]

    if start_date:
        filters.append("s.created_at >= ?")
        params.append(start_date)
    if end_date:
        filters.append("s.created_at <= ?")
        params.append(end_date)

    query = f"""
        SELECT
            f.lens AS lens,
            f.severity AS severity,
            COUNT(*) AS rejection_count
        FROM finding f
        JOIN session s ON s.id = f.session_id
        WHERE {' AND '.join(filters)}
        GROUP BY f.lens, f.severity
        ORDER BY rejection_count DESC, f.lens ASC, f.severity ASC
        LIMIT ?
    """
    params.append(bounded_limit)

    conn = get_connection(project_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [
            {
                "lens": row["lens"],
                "severity": row["severity"],
                "rejection_count": int(row["rejection_count"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_acceptance_rate_trend(
    project_path: Path,
    bucket: str = "daily",
    window: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return acceptance-rate trend points for daily/weekly buckets."""
    bucket_expr_by_name = {
        "daily": "date(s.created_at)",
        "weekly": "date(s.created_at, '-' || ((CAST(strftime('%w', s.created_at) AS INTEGER) + 6) % 7) || ' days')",
    }
    bucket_expr = bucket_expr_by_name.get(bucket)
    if bucket_expr is None:
        raise ValueError(f"Unsupported bucket: {bucket}")

    bounded_window = max(1, min(int(window), 366))
    filters = ["f.status IN ('accepted', 'rejected')"]
    params: list[object] = []

    if start_date:
        filters.append("s.created_at >= ?")
        params.append(start_date)
    if end_date:
        filters.append("s.created_at <= ?")
        params.append(end_date)

    query = f"""
        WITH aggregated AS (
            SELECT
                {bucket_expr} AS bucket_start,
                SUM(CASE WHEN f.status = 'accepted' THEN 1 ELSE 0 END) AS accepted_count,
                SUM(CASE WHEN f.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
            FROM finding f
            JOIN session s ON s.id = f.session_id
            WHERE {' AND '.join(filters)}
            GROUP BY bucket_start
            ORDER BY bucket_start DESC
            LIMIT ?
        )
        SELECT bucket_start, accepted_count, rejected_count
        FROM aggregated
        ORDER BY bucket_start ASC
    """
    params.append(bounded_window)

    conn = get_connection(project_path)
    try:
        rows = conn.execute(query, params).fetchall()
        trend_points: list[dict] = []
        for row in rows:
            accepted_count = int(row["accepted_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            sample_size = accepted_count + rejected_count
            acceptance_rate = accepted_count / sample_size if sample_size else 0.0
            trend_points.append(
                {
                    "bucket_start": row["bucket_start"],
                    "accepted_count": accepted_count,
                    "rejected_count": rejected_count,
                    "sample_size": sample_size,
                    "acceptance_rate": round(acceptance_rate, 4),
                }
            )
        return trend_points
    finally:
        conn.close()


def get_scene_finding_history(
    project_path: Path,
    scene_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return findings for a scene across sessions, newest-first with pagination."""
    if not scene_id:
        return []

    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    query = """
        SELECT
            f.id,
            f.session_id,
            f.number,
            f.severity,
            f.lens,
            f.location,
            f.line_start,
            f.line_end,
            f.scene_path,
            f.evidence,
            f.impact,
            f.options,
            f.flagged_by,
            f.ambiguity_type,
            f.stale,
            f.status,
            f.author_response,
            f.discussion_turns,
            f.revision_history,
            f.outcome_reason,
            f.origin,
            s.created_at AS session_created_at,
            s.completed_at AS session_completed_at,
            s.status AS session_status
        FROM finding f
        JOIN session s ON s.id = f.session_id
        WHERE f.scene_path = ?
        ORDER BY s.created_at DESC, s.id DESC, f.id DESC
        LIMIT ? OFFSET ?
    """

    # scene_id may be absolute; DB stores relative paths after v13 migration
    stored_scene_id = to_relative(project_path, scene_id)

    conn = get_connection(project_path)
    try:
        rows = conn.execute(query, (stored_scene_id, bounded_limit, bounded_offset)).fetchall()
        result: list[dict] = []
        for row in rows:
            entry = dict(row)
            for key in ("options", "flagged_by", "discussion_turns", "revision_history"):
                if isinstance(entry.get(key), str):
                    try:
                        entry[key] = json.loads(entry[key])
                    except (json.JSONDecodeError, TypeError):
                        entry[key] = []
            entry["stale"] = bool(entry.get("stale", 0))
            # Absolutize scene_path before returning
            if entry.get("scene_path"):
                abs_path = to_absolute(project_path, entry["scene_path"])
                if abs_path is not None:
                    entry["scene_path"] = str(abs_path)
            result.append(entry)
        return result
    finally:
        conn.close()


def get_finding_index_context_for_session(
    project_path: Path,
    session_id: int,
    finding_number: int,
    *,
    scopes: list[str] | None = None,
    max_matches_per_scope: int = 3,
) -> dict:
    """Return deterministic index context for a persisted finding in a session."""
    conn = get_connection(project_path)
    try:
        row = conn.execute(
            """
            SELECT
                location,
                evidence,
                impact,
                author_response,
                options
            FROM finding
            WHERE session_id = ? AND number = ?
            """,
            (session_id, finding_number),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {
            "filters": {
                "scopes": list(scopes or ["cast", "glossary"]),
                "max_matches_per_scope": max(1, int(max_matches_per_scope)),
            },
            "summary": {
                "candidate_entry_count": 0,
                "match_count": 0,
            },
            "rows": [],
        }

    finding_payload = {
        "location": row["location"] or "",
        "evidence": row["evidence"] or "",
        "impact": row["impact"] or "",
        "author_response": row["author_response"] or "",
        "options": [],
    }
    options_raw = row["options"]
    if isinstance(options_raw, str) and options_raw.strip():
        try:
            decoded = json.loads(options_raw)
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, list):
            finding_payload["options"] = [str(item) for item in decoded]

    return get_finding_index_context(
        project_path,
        finding_payload,
        scopes=scopes,
        max_matches_per_scope=max_matches_per_scope,
    )


def validate_session(
    session_data: dict,
    scene_content: str,
    scene_path: str,
    scene_paths: list[str] | None = None,
) -> tuple[bool, str]:
    """Validate that a saved session matches the current scene."""
    if not session_data:
        return False, "No session data"

    saved_scene_paths = session_data.get("scene_paths") or [session_data.get("scene_path", "")]
    requested_scene_paths = scene_paths or [scene_path]
    if {str(Path(p).resolve()) for p in saved_scene_paths if p} != {
        str(Path(p).resolve()) for p in requested_scene_paths if p
    }:
        return False, f"Session is for different scene set: {saved_scene_paths}"

    saved_hash = session_data.get("scene_hash", "")
    current_hash = compute_scene_hash(scene_content)
    if saved_hash != current_hash:
        return False, "Scene file has been modified since session was saved"

    return True, ""


def persist_finding(state: SessionState, finding: Finding) -> None:
    """Auto-save a finding's current state to the database."""
    if not state.db_conn or not state.session_id:
        return

    FindingStore.update(
        state.db_conn, state.session_id, finding.number,
        severity=finding.severity,
        lens=finding.lens,
        location=finding.location,
        line_start=finding.line_start,
        line_end=finding.line_end,
        scene_path=finding.scene_path,
        evidence=finding.evidence,
        impact=finding.impact,
        options=finding.options,
        flagged_by=finding.flagged_by,
        ambiguity_type=finding.ambiguity_type,
        stale=finding.stale,
        status=finding.status,
        author_response=finding.author_response,
        discussion_turns=finding.discussion_turns,
        revision_history=finding.revision_history,
        outcome_reason=finding.outcome_reason,
    )

    SessionStore.update_counts(state.db_conn, state.session_id)
    _sync_session_completion_state(state)


def persist_session_index(state: SessionState, current_index: int) -> None:
    """Auto-save the current finding index."""
    if not state.db_conn or not state.session_id:
        return
    SessionStore.update_index(state.db_conn, state.session_id, current_index)


def persist_discussion_history(state: SessionState) -> None:
    """Auto-save the discussion history."""
    if not state.db_conn or not state.session_id:
        return
    SessionStore.update_discussion_history(
        state.db_conn, state.session_id, state.discussion_history
    )


def _persist_learning_session(state: SessionState) -> None:
    """Auto-save in-session learning data (raw session blob on the session row)."""
    if not state.db_conn or not state.session_id:
        return
    learning_session = learning_session_payload(state.learning)
    SessionStore.update_learning_session(
        state.db_conn, state.session_id, learning_session
    )


def persist_session_learning(state: SessionState) -> None:
    """Persist in-session learning data and immediately commit new entries to the DB.

    This is the single chokepoint called after every learning-producing user
    action (reject, ambiguity answer, discussion preference).  It:

    1. Saves the raw session lists to the session row (for resume / audit).
    2. Drains those lists by writing each new entry directly to
       ``learning_entry`` via ``commit_pending_learning_entries()``.

    ``review_count`` is not touched here — see ``complete_session()`` for that.
    """
    _persist_learning_session(state)
    if state.db_conn:
        from lit_platform.services.learning_service import commit_pending_learning_entries
        commit_pending_learning_entries(state.learning, state.db_conn)


def _read_current_scene_content(state: SessionState) -> Optional[str]:
    """Read and (re-)concatenate scene content from disk.

    For multi-scene sessions, reads all scene files and concatenates them
    with boundary markers (matching the original analysis layout).
    For single-scene sessions, reads the single file directly.

    Returns the new content string, or *None* if any file is missing / unreadable.
    """
    scene_paths = getattr(state, "scene_paths", None) or [state.scene_path]

    if len(scene_paths) > 1:
        scene_docs: list[tuple[str, str]] = []
        for sp in scene_paths:
            p = Path(sp)
            if not p.exists():
                return None
            try:
                scene_docs.append((sp, p.read_text(encoding="utf-8")))
            except IOError:
                return None
        new_content, _line_map = concatenate_scenes(scene_docs)
        return new_content

    # Single-scene fast path
    scene_path = Path(state.scene_path)
    if not scene_path.exists():
        return None
    try:
        return scene_path.read_text(encoding="utf-8")
    except IOError:
        return None


async def detect_and_apply_scene_changes(state: SessionState,
                                         current_index: int) -> Optional[dict]:
    """Check if any scene file has been modified and handle the change.

    Supports both single-scene and multi-scene sessions.  For multi-scene
    sessions all scene files are re-read and re-concatenated before hashing.
    """
    new_content = _read_current_scene_content(state)
    if new_content is None:
        return None

    old_hash = compute_scene_hash(state.scene_content)
    new_hash = compute_scene_hash(new_content)
    if old_hash == new_hash:
        return None

    old_content = state.scene_content
    change_summary = apply_scene_change(
        state.findings, old_content, new_content, start_index=current_index
    )

    state.scene_content = new_content
    if state.db_conn and state.session_id:
        SessionStore.update_scene(state.db_conn, state.session_id, new_hash)

    for finding in state.findings[current_index:]:
        persist_finding(state, finding)

    stale_findings = [
        f for f in state.findings[current_index:]
        if f.stale and f.status not in ("withdrawn", "rejected")
    ]

    checker_model_id = getattr(state, "effective_checker_model_id", state.model_id)

    re_eval_results = []
    if stale_findings:
        from lit_platform.runtime.api import re_evaluate_finding

        for finding in stale_findings:
            result = await re_evaluate_finding(
                state.client, finding, new_content,
                model=checker_model_id, max_tokens=1024,
            )
            re_eval_results.append(result)
            persist_finding(state, finding)

    return {
        "changed": True,
        "adjusted": change_summary["adjusted"],
        "stale": change_summary["stale"],
        "no_lines": change_summary["no_lines"],
        "re_evaluated": re_eval_results,
    }


async def review_current_finding_against_scene_edits(
    state: SessionState,
    current_index: int,
) -> dict:
    """Re-check only the current finding against scene edits.

    Supports both single-scene and multi-scene sessions via
    ``_read_current_scene_content()``.
    """
    if current_index < 0 or current_index >= len(state.findings):
        return {
            "changed": False,
            "adjusted": 0,
            "stale": 0,
            "no_lines": 0,
            "re_evaluated": [],
            "message": "No active finding to review.",
        }

    new_content = _read_current_scene_content(state)
    if new_content is None:
        return {
            "changed": False,
            "adjusted": 0,
            "stale": 0,
            "no_lines": 0,
            "re_evaluated": [],
            "message": "Scene file not found or unreadable.",
        }

    old_hash = compute_scene_hash(state.scene_content)
    new_hash = compute_scene_hash(new_content)
    if old_hash == new_hash:
        return {
            "changed": False,
            "adjusted": 0,
            "stale": 0,
            "no_lines": 0,
            "re_evaluated": [],
            "message": "No scene changes detected.",
        }

    old_content = state.scene_content
    change_summary = apply_scene_change(
        state.findings, old_content, new_content, start_index=current_index
    )

    state.scene_content = new_content
    if state.db_conn and state.session_id:
        SessionStore.update_scene(state.db_conn, state.session_id, new_hash)

    for finding in state.findings[current_index:]:
        persist_finding(state, finding)

    checker_model_id = getattr(state, "effective_checker_model_id", state.model_id)

    finding = state.findings[current_index]
    re_eval_results = []
    if finding.status not in ("withdrawn", "rejected"):
        from lit_platform.runtime.api import re_evaluate_finding

        result = await re_evaluate_finding(
            state.client, finding, new_content,
            model=checker_model_id, max_tokens=1024,
        )
        re_eval_results.append(result)
        persist_finding(state, finding)

    return {
        "changed": True,
        "adjusted": change_summary["adjusted"],
        "stale": change_summary["stale"],
        "no_lines": change_summary["no_lines"],
        "re_evaluated": re_eval_results,
    }
