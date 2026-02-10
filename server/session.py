"""
Session persistence for the lit-critic system.
Handles saving and loading review sessions, and scene change detection.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import SESSION_FILE
from .models import SessionState, Finding
from .utils import apply_scene_change

logger = logging.getLogger(__name__)


def compute_scene_hash(scene_content: str) -> str:
    """Compute a hash of the scene content for change detection."""
    return hashlib.sha256(scene_content.encode('utf-8')).hexdigest()[:16]


def get_session_file_path(project_path: Path) -> Path:
    """Get the path to the session file."""
    return project_path / SESSION_FILE


def session_exists(project_path: Path) -> bool:
    """Check if a saved session exists."""
    return get_session_file_path(project_path).exists()


def save_session(state: SessionState, current_index: int, skip_minor: bool = False) -> Path:
    """
    Save the current session state to a JSON file.
    Returns the path to the saved session file.
    """
    session_data = {
        "version": 1,
        "saved_at": datetime.now().isoformat(),
        "scene_path": str(state.scene_path),
        "scene_hash": compute_scene_hash(state.scene_content),
        "model": state.model,
        "current_index": current_index,
        "skip_minor": skip_minor,
        "glossary_issues": state.glossary_issues,
        "findings": [f.to_dict(include_state=True) for f in state.findings],
        "discussion_history": state.discussion_history,
        "learning_session": {
            "session_rejections": state.learning.session_rejections,
            "session_acceptances": state.learning.session_acceptances,
            "session_ambiguity_answers": state.learning.session_ambiguity_answers,
        }
    }
    
    filepath = get_session_file_path(state.project_path)
    filepath.write_text(json.dumps(session_data, indent=2), encoding='utf-8')
    return filepath


def load_session(project_path: Path) -> Optional[dict]:
    """
    Load a saved session from the project directory.
    Returns the session data dict, or None if no session exists.
    """
    filepath = get_session_file_path(project_path)
    if not filepath.exists():
        return None
    
    try:
        content = filepath.read_text(encoding='utf-8')
        return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load session file: {e}")
        return None


def delete_session(project_path: Path) -> bool:
    """Delete the session file. Returns True if deleted, False if not found."""
    filepath = get_session_file_path(project_path)
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def validate_session(session_data: dict, scene_content: str, scene_path: str) -> tuple[bool, str]:
    """
    Validate that a saved session matches the current scene.
    Returns (is_valid, error_message).
    """
    if not session_data:
        return False, "No session data"
    
    # Check scene path matches
    saved_scene_path = session_data.get("scene_path", "")
    if Path(saved_scene_path).resolve() != Path(scene_path).resolve():
        return False, f"Session is for different scene: {saved_scene_path}"
    
    # Check scene content hasn't changed
    saved_hash = session_data.get("scene_hash", "")
    current_hash = compute_scene_hash(scene_content)
    if saved_hash != current_hash:
        return False, "Scene file has been modified since session was saved"
    
    return True, ""


async def detect_and_apply_scene_changes(state: SessionState, current_index: int) -> Optional[dict]:
    """Check if the scene file has been modified and handle the change.

    This is the single chokepoint for scene change detection, called by both
    CLI and Web UI before each finding transition.

    If the scene file has changed:
    1. Compute diff and adjust line numbers for remaining findings
    2. Automatically re-evaluate any stale findings via the API
    3. Update ``state.scene_content`` to the new version

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

    return {
        "changed": True,
        "adjusted": change_summary["adjusted"],
        "stale": change_summary["stale"],
        "no_lines": change_summary["no_lines"],
        "re_evaluated": re_eval_results,
    }
