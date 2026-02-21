"""
Session persistence for the lit-critic system.

Uses SQLite via ``server.db`` for all persistence.  Every mutation is
auto-saved — callers do not need an explicit "save" step.

Public API
----------
Scene hashing / validation:
    compute_scene_hash(scene_content) → str
    validate_session(session_data, scene_content, scene_path) → (bool, str)

Session lifecycle:
    create_session(state, glossary_issues) → int          # after analysis
    check_active_session(project_path) → dict | None      # for "overwrite?" prompt
    load_active_session(project_path) → dict | None       # full load for resume
    load_session_by_id(project_path, session_id) → dict | None
    complete_session(state)
    abandon_session(state)
    delete_session_by_id(project_path, session_id) → bool

Auto-save helpers (called after every mutation):
    persist_finding(state, finding)
    persist_session_index(state, current_index)
    persist_session_learning(state)
    persist_discussion_history(state)

Scene change detection:
    detect_and_apply_scene_changes(state, current_index) → dict | None
"""

import asyncio
import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

from lit_platform.session_state_machine import (
    all_findings_considered as platform_all_findings_considered,
    first_unresolved_index,
    is_terminal_status,
    learning_session_payload,
)

from .db import (
    get_connection, SessionStore, FindingStore,
)
from .models import SessionState, Finding
from .utils import apply_scene_change

logger = logging.getLogger(__name__)

SQLITE_LOCK_RETRY_ATTEMPTS = 3
SQLITE_LOCK_RETRY_BACKOFF_SECONDS = 0.02


def _run_with_sqlite_lock_retry(operation, *, operation_name: str) -> None:
    """Run a DB mutation with bounded retries for transient SQLite lock errors."""
    for attempt in range(1, SQLITE_LOCK_RETRY_ATTEMPTS + 1):
        try:
            operation()
            return
        except sqlite3.OperationalError as exc:
            is_lock_error = "locked" in str(exc).lower()
            if not is_lock_error or attempt >= SQLITE_LOCK_RETRY_ATTEMPTS:
                raise
            wait = SQLITE_LOCK_RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "SQLite lock during %s (attempt %d/%d). Retrying in %.3fs",
                operation_name,
                attempt,
                SQLITE_LOCK_RETRY_ATTEMPTS,
                wait,
            )
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Scene hashing
# ---------------------------------------------------------------------------


def compute_scene_hash(scene_content: str) -> str:
    """Compute a hash of the scene content for change detection."""
    return hashlib.sha256(scene_content.encode('utf-8')).hexdigest()[:16]


def is_terminal_finding_status(status: str) -> bool:
    """Return True when a finding status counts as fully considered."""
    return is_terminal_status(status)


def all_findings_considered(findings: list[Finding]) -> bool:
    """Return True when every finding is in a terminal status."""
    return platform_all_findings_considered(findings)


def first_unresolved_finding_index(findings: list[Finding]) -> Optional[int]:
    """Return the index of the first non-terminal finding, or None."""
    return first_unresolved_index(findings)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def create_session(state: SessionState, glossary_issues: list[str] | None = None) -> int:
    """Create a new active session in the database and persist all findings.

    Called after analysis completes.  Populates ``state.session_id`` and
    ``state.db_conn``.

    Returns the new session id.
    """
    conn = get_connection(state.project_path)
    state.db_conn = conn

    scene_hash = compute_scene_hash(state.scene_content)
    session_id = SessionStore.create(
        conn,
        scene_path=state.scene_path,
        scene_hash=scene_hash,
        model=state.model,
        glossary_issues=glossary_issues or state.glossary_issues,
        discussion_model=state.discussion_model,
        lens_preferences=state.lens_preferences,
    )
    state.session_id = session_id

    # Persist all findings
    findings_dicts = [f.to_dict(include_state=True) for f in state.findings]
    FindingStore.save_all(conn, session_id, findings_dicts)

    # Update total_findings count now that findings are saved
    conn.execute(
        "UPDATE session SET total_findings = ? WHERE id = ?",
        (len(findings_dicts), session_id),
    )
    conn.commit()

    # Persist initial learning session data
    _persist_learning_session(state)

    return session_id


def check_active_session(project_path: Path) -> Optional[dict]:
    """Check if an active session exists for the project.

    Returns a summary dict with keys ``exists``, ``scene_path``,
    ``created_at``, ``current_index``, ``total_findings``, or
    ``{"exists": False}`` if no active session.
    """
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.load_active(conn)
        if session_data is None:
            return {"exists": False}

        findings = FindingStore.load_all(conn, session_data["id"])
        return {
            "exists": True,
            "session_id": session_data["id"],
            "scene_path": session_data.get("scene_path", ""),
            "created_at": session_data.get("created_at", ""),
            "current_index": session_data.get("current_index", 0),
            "total_findings": len(findings),
            "model": session_data.get("model", ""),
            "discussion_model": session_data.get("discussion_model"),
            "lens_preferences": session_data.get("lens_preferences", {}),
        }
    finally:
        conn.close()


def load_active_session(project_path: Path) -> Optional[dict]:
    """Load the full active session data including findings.

    Returns a dict compatible with the old ``load_session()`` shape,
    or ``None`` if no active session exists.
    """
    conn = get_connection(project_path)
    session_data = SessionStore.load_active(conn)
    if session_data is None:
        conn.close()
        return None

    findings = FindingStore.load_all(conn, session_data["id"])
    
    # Update counts based on actual finding statuses
    # (they may be stale if the session was saved before we added real-time count updates)
    SessionStore.update_counts(conn, session_data["id"])
    
    # Reload session data to get updated counts
    session_data = SessionStore.get(conn, session_data["id"])

    # Return in a shape that the consumers expect
    return {
        "_conn": conn,  # Caller takes ownership of the connection
        "session_id": session_data["id"],
        "scene_path": session_data.get("scene_path", ""),
        "scene_hash": session_data.get("scene_hash", ""),
        "model": session_data.get("model", ""),
        "discussion_model": session_data.get("discussion_model"),  # None = use analysis model
        "lens_preferences": session_data.get("lens_preferences", {}),
        "current_index": session_data.get("current_index", 0),
        "glossary_issues": session_data.get("glossary_issues", []),
        "discussion_history": session_data.get("discussion_history", []),
        "learning_session": session_data.get("learning_session", {}),
        "findings": findings,
        "created_at": session_data.get("created_at", ""),
        "accepted_count": session_data.get("accepted_count", 0),
        "rejected_count": session_data.get("rejected_count", 0),
        "withdrawn_count": session_data.get("withdrawn_count", 0),
    }


def load_session_by_id(project_path: Path, session_id: int) -> Optional[dict]:
    """Load a specific session by id including findings.

    Returns a dict compatible with ``load_active_session()`` shape,
    or ``None`` if the session id does not exist.
    """
    conn = get_connection(project_path)
    session_data = SessionStore.get(conn, session_id)
    if session_data is None:
        conn.close()
        return None

    # Keep counts fresh for active sessions.
    if session_data.get("status") == "active":
        SessionStore.update_counts(conn, session_id)
        session_data = SessionStore.get(conn, session_id)

    findings = FindingStore.load_all(conn, session_id)

    return {
        "_conn": conn,  # Caller takes ownership of the connection
        "session_id": session_data["id"],
        "scene_path": session_data.get("scene_path", ""),
        "scene_hash": session_data.get("scene_hash", ""),
        "model": session_data.get("model", ""),
        "discussion_model": session_data.get("discussion_model"),
        "lens_preferences": session_data.get("lens_preferences", {}),
        "current_index": session_data.get("current_index", 0),
        "glossary_issues": session_data.get("glossary_issues", []),
        "discussion_history": session_data.get("discussion_history", []),
        "learning_session": session_data.get("learning_session", {}),
        "findings": findings,
        "created_at": session_data.get("created_at", ""),
        "status": session_data.get("status", "active"),
        "accepted_count": session_data.get("accepted_count", 0),
        "rejected_count": session_data.get("rejected_count", 0),
        "withdrawn_count": session_data.get("withdrawn_count", 0),
    }


def complete_session(state: SessionState) -> bool:
    """Mark the active session as completed iff all findings are terminal.

    Returns True when the session was completed, False otherwise.
    """
    if not state.db_conn or not state.session_id:
        return False
    if not all_findings_considered(state.findings):
        return False
    SessionStore.complete(state.db_conn, state.session_id)
    return True


def abandon_session(state: SessionState) -> None:
    """Mark the active session as abandoned."""
    if state.db_conn and state.session_id:
        SessionStore.abandon(state.db_conn, state.session_id)


def abandon_active_session(project_path: Path) -> bool:
    """Find and abandon the active session (if any). Returns True if abandoned."""
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.load_active(conn)
        if session_data is None:
            return False
        SessionStore.abandon(conn, session_data["id"])
        return True
    finally:
        conn.close()


def complete_active_session(project_path: Path) -> bool:
    """Find and complete the active session (if any). Returns True if completed."""
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.load_active(conn)
        if session_data is None:
            return False
        findings = FindingStore.load_all(conn, session_data["id"])
        if any(not is_terminal_status(f.get("status", "pending")) for f in findings):
            return False
        SessionStore.complete(conn, session_data["id"])
        return True
    finally:
        conn.close()


def _sync_session_completion_state(state: SessionState) -> None:
    """Keep persisted session status aligned with finding terminality.

    - Completes the session when all findings are terminal.
    - Reopens a completed session when any finding becomes non-terminal.
    """
    if not state.db_conn or not state.session_id:
        return

    session_row = SessionStore.get(state.db_conn, state.session_id)
    if not session_row:
        return

    complete_now = all_findings_considered(state.findings)
    status = session_row.get("status")

    if complete_now and status != "completed":
        SessionStore.complete(state.db_conn, state.session_id)
    elif not complete_now and status == "completed":
        SessionStore.reopen(state.db_conn, state.session_id)


def delete_session_by_id(project_path: Path, session_id: int) -> bool:
    """Delete a specific session by id. Returns True if deleted."""
    conn = get_connection(project_path)
    try:
        return SessionStore.delete(conn, session_id)
    finally:
        conn.close()


def list_sessions(project_path: Path) -> list[dict]:
    """List all sessions for the project, newest first."""
    conn = get_connection(project_path)
    try:
        return SessionStore.list_all(conn)
    finally:
        conn.close()


def get_session_detail(project_path: Path, session_id: int) -> Optional[dict]:
    """Get a session and its findings by id."""
    conn = get_connection(project_path)
    try:
        session_data = SessionStore.get(conn, session_id)
        if session_data is None:
            return None
        
        # Update counts for active sessions (may be stale)
        if session_data.get("status") == "active":
            SessionStore.update_counts(conn, session_id)
            session_data = SessionStore.get(conn, session_id)
        
        findings = FindingStore.load_all(conn, session_id)
        session_data["findings"] = findings
        return session_data
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_session(session_data: dict, scene_content: str,
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
    current_hash = compute_scene_hash(scene_content)
    if saved_hash != current_hash:
        return False, "Scene file has been modified since session was saved"

    return True, ""


# ---------------------------------------------------------------------------
# Auto-save helpers
# ---------------------------------------------------------------------------


def persist_finding(state: SessionState, finding: Finding) -> None:
    """Auto-save a finding's current state to the database.

    Call this after any mutation to a finding (accept, reject, discuss, etc.).
    Silently skipped when ``state.db_conn`` is None (e.g. in tests).
    """
    if not state.db_conn or not state.session_id:
        return

    _run_with_sqlite_lock_retry(
        lambda: FindingStore.update(
            state.db_conn, state.session_id, finding.number,
            severity=finding.severity,
            lens=finding.lens,
            location=finding.location,
            line_start=finding.line_start,
            line_end=finding.line_end,
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
        ),
        operation_name="persist_finding",
    )
    
    # Update session counts whenever a finding status changes
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
    """Auto-save the in-session learning data (raw session blob on the session row)."""
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
        from .learning import commit_pending_learning_entries
        commit_pending_learning_entries(state.learning, state.db_conn)


# ---------------------------------------------------------------------------
# Scene change detection
# ---------------------------------------------------------------------------


async def detect_and_apply_scene_changes(state: SessionState,
                                         current_index: int) -> Optional[dict]:
    """Check if the scene file has been modified and handle the change.

    This is the single chokepoint for scene change detection, called by both
    CLI and Web UI before each finding transition.

    If the scene file has changed:
    1. Compute diff and adjust line numbers for remaining findings
    2. Automatically re-evaluate any stale findings via the API
    3. Update ``state.scene_content`` to the new version
    4. Auto-save all affected findings to the database

    Returns ``None`` if the scene is unchanged, or a summary dict:
        changed    – True
        adjusted   – number of findings whose lines were shifted
        stale      – number of findings originally marked stale
        re_evaluated – list of {finding_number, status, reason?} dicts
    """
    scene_path = Path(state.scene_path)
    if not scene_path.exists():
        return None

    try:
        new_content = scene_path.read_text(encoding='utf-8')
    except IOError:
        return None

    old_hash = compute_scene_hash(state.scene_content)
    new_hash = compute_scene_hash(new_content)

    if old_hash == new_hash:
        return None

    # Scene has changed — compute diff and adjust findings
    old_content = state.scene_content
    change_summary = apply_scene_change(
        state.findings, old_content, new_content, start_index=current_index
    )

    # Update state to the new scene content
    state.scene_content = new_content

    # Update scene hash in DB
    if state.db_conn and state.session_id:
        SessionStore.update_scene(state.db_conn, state.session_id, new_hash)

    # Auto-save all adjusted/stale findings
    for finding in state.findings[current_index:]:
        persist_finding(state, finding)

    # Collect stale findings for re-evaluation
    stale_findings = [
        f for f in state.findings[current_index:]
        if f.stale and f.status not in ("withdrawn", "rejected")
    ]

    re_eval_results = []
    if stale_findings:
        # Import here to avoid circular imports
        from .api import re_evaluate_finding

        for finding in stale_findings:
            result = await re_evaluate_finding(
                state.client, finding, new_content,
                model=state.model_id, max_tokens=1024
            )
            re_eval_results.append(result)
            # Auto-save after re-evaluation
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

    Unlike ``detect_and_apply_scene_changes()``, this function only asks the
    LLM to reconsider the *current* finding after applying scene diff/line
    remapping updates.
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

    scene_path = Path(state.scene_path)
    if not scene_path.exists():
        return {
            "changed": False,
            "adjusted": 0,
            "stale": 0,
            "no_lines": 0,
            "re_evaluated": [],
            "message": "Scene file not found.",
        }

    try:
        new_content = scene_path.read_text(encoding="utf-8")
    except IOError:
        return {
            "changed": False,
            "adjusted": 0,
            "stale": 0,
            "no_lines": 0,
            "re_evaluated": [],
            "message": "Could not read scene file.",
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

    finding = state.findings[current_index]
    re_eval_results = []
    if finding.status not in ("withdrawn", "rejected"):
        from .api import re_evaluate_finding

        result = await re_evaluate_finding(
            state.client, finding, new_content,
            model=state.model_id, max_tokens=1024,
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
