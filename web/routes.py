"""
REST API routes for the lit-critic Web UI.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from lit_platform.repo_preflight import MARKER_FILENAME, validate_repo_path
from lit_platform.user_config import get_repo_path, set_repo_path
from lit_platform.persistence import LearningStore, get_connection
from lit_platform.services.analysis_service import (
    API_KEY_ENV_VARS,
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    LENS_PRESETS,
    normalize_lens_preferences,
)
from lit_platform.services import (
    check_active_session,
    get_session_detail,
    list_sessions,
    delete_session_by_id,
    load_learning,
    export_learning_markdown,
)
from .session_manager import WebSessionManager, ResumeScenePathError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Single shared session manager (single-user local tool)
session_mgr = WebSessionManager()


# --- Request models ---

class AnalyzeRequest(BaseModel):
    scene_path: str
    project_path: str
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    model: Optional[str] = None
    discussion_model: Optional[str] = None
    lens_preferences: Optional[dict] = None


class ResumeRequest(BaseModel):
    project_path: str
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    scene_path_override: Optional[str] = None


class ResumeSessionByIdRequest(BaseModel):
    project_path: str
    session_id: int
    api_key: Optional[str] = None
    discussion_api_key: Optional[str] = None
    scene_path_override: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str = ""


class DiscussRequest(BaseModel):
    message: str


class GotoRequest(BaseModel):
    index: int


class AmbiguityRequest(BaseModel):
    intentional: bool


class CheckSessionRequest(BaseModel):
    project_path: str


class ProjectPathRequest(BaseModel):
    project_path: str


class SessionIdRequest(BaseModel):
    project_path: str
    session_id: int


class LearningEntryDeleteRequest(BaseModel):
    project_path: str
    entry_id: int


class RepoPathUpdateRequest(BaseModel):
    repo_path: str


# --- Helper ---

def _normalise_model_name(name: Optional[str], default: str = DEFAULT_MODEL) -> str:
    """Return a valid model short name, falling back to ``default``."""
    if name and name in AVAILABLE_MODELS:
        return name
    return default


def _normalise_optional_model_name(name: Optional[str]) -> Optional[str]:
    """Return a valid optional model short name, or ``None``."""
    if name and name in AVAILABLE_MODELS:
        return name
    return None


def _validate_api_key_matches_provider(provider: str, key: str, key_label: str) -> None:
    """Best-effort guardrail for obvious provider/key mismatches.

    - Anthropic keys are expected to start with ``sk-ant-``.
    - OpenAI keys should *not* start with ``sk-ant-``.
    """
    trimmed = key.strip()

    if provider == "openai" and trimmed.startswith("sk-ant-"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{key_label} appears to be an Anthropic key, but the selected model uses OpenAI. "
                "Provide an OpenAI key (OPENAI_API_KEY or discussion_api_key/api_key as appropriate)."
            ),
        )

    if provider == "anthropic" and trimmed.startswith("sk-") and not trimmed.startswith("sk-ant-"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{key_label} appears to be an OpenAI key, but the selected model uses Anthropic. "
                "Provide an Anthropic key (ANTHROPIC_API_KEY or discussion_api_key/api_key as appropriate)."
            ),
        )


def _resolve_provider_api_key(provider: str, explicit_key: Optional[str], key_label: str) -> str:
    """Resolve an API key for a specific provider.

    Resolution order:
    1. Explicit key from request.
    2. Provider-specific environment variable.
    """
    if explicit_key:
        _validate_api_key_matches_provider(provider, explicit_key, key_label)
        return explicit_key

    env_var = API_KEY_ENV_VARS.get(provider)
    env_key = os.environ.get(env_var) if env_var else None
    if env_key:
        _validate_api_key_matches_provider(provider, env_key, env_var or key_label)
        return env_key

    raise HTTPException(
        status_code=400,
        detail=(
            f"No API key for provider '{provider}' ({key_label}). "
            f"Provide {key_label} in request body or set {env_var}."
        ),
    )


def _repo_preflight_payload() -> dict:
    configured = get_repo_path()
    validation = validate_repo_path(configured)
    return {
        "ok": validation.ok,
        "reason_code": validation.reason_code,
        "message": validation.message,
        "path": validation.path,
        "marker": MARKER_FILENAME,
        "configured_path": configured,
    }


def _ensure_repo_preflight_ready() -> None:
    payload = _repo_preflight_payload()
    if payload["ok"]:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "repo_path_invalid",
            **payload,
            "next_action": "Provide a valid lit-critic installation path via POST /api/repo-path.",
        },
    )


def _resolve_analysis_and_discussion_keys(
    model: str,
    discussion_model: Optional[str],
    api_key: Optional[str],
    discussion_api_key: Optional[str],
) -> tuple[str, Optional[str]]:
    """Resolve provider-correct keys for analysis and discussion models."""
    analysis_provider = AVAILABLE_MODELS[model]["provider"]
    analysis_key = _resolve_provider_api_key(
        analysis_provider,
        api_key,
        "api_key",
    )

    if not discussion_model:
        return analysis_key, None

    discussion_provider = AVAILABLE_MODELS[discussion_model]["provider"]

    if discussion_provider == analysis_provider:
        # Same provider: discussion key is optional. If provided, validate and use it.
        if discussion_api_key:
            discussion_key = _resolve_provider_api_key(
                discussion_provider,
                discussion_api_key,
                "discussion_api_key",
            )
            return analysis_key, discussion_key
        return analysis_key, None

    # Cross-provider: discussion provider key must be resolved independently.
    discussion_key = _resolve_provider_api_key(
        discussion_provider,
        discussion_api_key,
        "discussion_api_key",
    )
    return analysis_key, discussion_key


# --- Routes ---

@router.get("/config")
async def get_config():
    """Return non-secret configuration state for the frontend."""
    # Report which providers have API keys configured
    api_keys_configured = {
        provider: bool(os.environ.get(env_var))
        for provider, env_var in API_KEY_ENV_VARS.items()
    }

    return {
        "api_key_configured": any(api_keys_configured.values()),
        "api_keys_configured": api_keys_configured,
        "available_models": {
            name: {"label": cfg["label"], "provider": cfg["provider"]}
            for name, cfg in AVAILABLE_MODELS.items()
        },
        "default_model": DEFAULT_MODEL,
        "lens_presets": LENS_PRESETS,
    }


@router.get("/repo-preflight")
async def get_repo_preflight():
    """Return preflight validation status for configured repo path."""
    return _repo_preflight_payload()


@router.post("/repo-path")
async def update_repo_path(req: RepoPathUpdateRequest):
    """Validate and persist the repo path in user-level config."""
    validation = validate_repo_path(req.repo_path)
    if not validation.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "repo_path_invalid",
                "ok": validation.ok,
                "reason_code": validation.reason_code,
                "message": validation.message,
                "path": validation.path,
                "marker": MARKER_FILENAME,
            },
        )

    assert validation.path is not None
    set_repo_path(validation.path)
    return _repo_preflight_payload()


@router.post("/analyze")
async def start_analysis(req: AnalyzeRequest):
    """Start a new multi-lens analysis."""
    _ensure_repo_preflight_ready()

    model = _normalise_model_name(req.model)
    discussion_model = _normalise_optional_model_name(req.discussion_model)

    analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
        model,
        discussion_model,
        req.api_key,
        req.discussion_api_key,
    )

    try:
        lens_preferences = normalize_lens_preferences(req.lens_preferences)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        result = await session_mgr.start_analysis(
            req.scene_path,
            req.project_path,
            analysis_key,
            model=model,
            discussion_model=discussion_model,
            discussion_api_key=discussion_key,
            lens_preferences=lens_preferences,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/analyze/progress")
async def analysis_progress(request: Request):
    """SSE endpoint that streams analysis progress events."""
    progress = session_mgr.analysis_progress

    if progress is None:
        raise HTTPException(status_code=404, detail="No analysis in progress")

    async def event_stream():
        # First, send any already-emitted events
        sent = 0
        for event in progress.events:
            yield f"data: {json.dumps(event)}\n\n"
            sent += 1

        # Then stream new events as they arrive
        while not progress.complete or sent < len(progress.events):
            try:
                event = await asyncio.wait_for(progress.get_event(), timeout=1.0)
                yield f"data: {json.dumps(event)}\n\n"
                sent += 1
            except asyncio.TimeoutError:
                # Send keepalive
                if progress.complete:
                    break
                yield f": keepalive\n\n"

            # Check if client disconnected
            if await request.is_disconnected():
                break

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/resume")
async def resume_session(req: ResumeRequest):
    """Resume the active session from SQLite."""
    _ensure_repo_preflight_ready()

    # Peek at the active session to determine providers for key resolution.
    active = check_active_session(Path(req.project_path))

    analysis_key: Optional[str] = req.api_key
    discussion_key: Optional[str] = req.discussion_api_key

    if active.get("exists"):
        saved_model = _normalise_model_name(active.get("model"), default=DEFAULT_MODEL)
        saved_discussion_model = _normalise_optional_model_name(active.get("discussion_model"))

        analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
            saved_model,
            saved_discussion_model,
            req.api_key,
            req.discussion_api_key,
        )

    try:
        result = await session_mgr.resume_session(
            req.project_path,
            analysis_key,
            discussion_api_key=discussion_key,
            scene_path_override=req.scene_path_override,
        )
    except ResumeScenePathError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scene_path_not_found",
                "message": str(e),
                "saved_scene_path": e.saved_scene_path,
                "attempted_scene_path": e.attempted_scene_path,
                "project_path": e.project_path,
                "override_provided": e.override_provided,
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.post("/resume-session")
async def resume_session_by_id(req: ResumeSessionByIdRequest):
    """Resume a specific active session by id from SQLite."""
    _ensure_repo_preflight_ready()

    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    detail = get_session_detail(project, req.session_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

    if detail.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Session {req.session_id} is '{detail.get('status')}' and cannot be resumed. "
                "Only active sessions can be resumed."
            ),
        )

    saved_model = _normalise_model_name(detail.get("model"), default=DEFAULT_MODEL)
    saved_discussion_model = _normalise_optional_model_name(detail.get("discussion_model"))

    analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
        saved_model,
        saved_discussion_model,
        req.api_key,
        req.discussion_api_key,
    )

    try:
        result = await session_mgr.resume_session_by_id(
            req.project_path,
            req.session_id,
            analysis_key,
            discussion_api_key=discussion_key,
            scene_path_override=req.scene_path_override,
        )
    except ResumeScenePathError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scene_path_not_found",
                "message": str(e),
                "saved_scene_path": e.saved_scene_path,
                "attempted_scene_path": e.attempted_scene_path,
                "project_path": e.project_path,
                "override_provided": e.override_provided,
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.post("/check-session")
async def check_saved_session(req: CheckSessionRequest):
    """Check if a saved session exists for the given project."""
    return session_mgr.check_saved_session(req.project_path)


@router.get("/session")
async def get_session():
    """Get current session info."""
    return session_mgr.get_session_info()


@router.get("/scene")
async def get_scene():
    """Get the scene text content."""
    content = session_mgr.get_scene_content()
    if content is None:
        raise HTTPException(status_code=404, detail="No active session")
    return {"content": content}


@router.get("/finding")
async def get_current_finding():
    """Get the current finding."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    finding = session_mgr.get_current_finding()
    if finding is None:
        return {"complete": True, "message": "All findings have been presented."}

    return {"complete": False, **finding}


@router.post("/finding/continue")
async def continue_finding():
    """Advance to the next finding, checking for scene changes first."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = await session_mgr.advance_with_scene_check()
    return result


@router.post("/finding/accept")
async def accept_finding():
    """Accept the current finding and advance (with scene change check)."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.accept_finding()
    next_result = await session_mgr.advance_with_scene_check()

    return {
        "action": result,
        "next": next_result,
    }


@router.post("/finding/reject")
async def reject_finding(req: RejectRequest):
    """Reject the current finding and advance (with scene change check)."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.reject_finding(req.reason)
    next_result = await session_mgr.advance_with_scene_check()

    return {
        "action": result,
        "next": next_result,
    }


@router.post("/finding/discuss")
async def discuss_finding(req: DiscussRequest):
    """Send a discussion message about the current finding."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = await session_mgr.discuss(req.message)
    return result


@router.post("/finding/discuss/stream")
async def discuss_finding_stream(req: DiscussRequest):
    """Stream discussion response token-by-token via SSE.

    Emits SSE events:
        {"type": "token", "text": "..."} — streaming text chunk
        {"type": "done", ...}            — final result (same shape as /finding/discuss response)
    """
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    async def event_stream():
        async for chunk_type, data in session_mgr.discuss_stream(req.message):
            if chunk_type == "scene_change":
                yield f"data: {json.dumps({'type': 'scene_change', **data})}\n\n"
            elif chunk_type == "token":
                yield f"data: {json.dumps({'type': 'token', 'text': data})}\n\n"
            elif chunk_type == "done":
                yield f"data: {json.dumps({'type': 'done', **data})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/finding/goto")
async def goto_finding(req: GotoRequest):
    """Jump to a specific finding by index (with scene change check).

    Allows the user to navigate to any finding in any order, not just
    sequentially.  The backend's current_index is updated so that
    subsequent accept/reject/discuss operations target the correct finding.
    """
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = await session_mgr.goto_finding_with_scene_check(req.index)
    return result


@router.post("/finding/ambiguity")
async def mark_ambiguity(req: AmbiguityRequest):
    """Mark current finding's ambiguity as intentional or accidental."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.mark_ambiguity(req.intentional)
    return result


@router.post("/finding/review")
async def review_finding():
    """Re-check the current finding against scene edits."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    return await session_mgr.review_current_finding()


@router.post("/finding/skip-to/{lens}")
async def skip_to_lens(lens: str):
    """Skip to findings from a specific lens group (structure or coherence)."""
    if lens not in ('structure', 'coherence'):
        raise HTTPException(status_code=400, detail="Lens must be 'structure' or 'coherence'")

    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    finding = session_mgr.skip_to_lens(lens)
    if finding is None:
        return {"complete": True, "message": "All findings have been presented."}

    return {"complete": False, **finding}


@router.post("/learning/save")
async def save_learning():
    """Export LEARNING.md to the project directory."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.save_learning()
    return result


# ---------------------------------------------------------------------------
# Management endpoints (Phase 2)
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions_route(project_path: str = Query(..., description="Path to the project directory")):
    """List all sessions for a project."""
    from pathlib import Path

    project = Path(project_path)
    
    # Log for debugging path encoding issues
    logger.info(f"GET /api/sessions: project_path={project_path!r}, exists={project.exists()}")
    
    if not project.exists():
        logger.warning(f"Project directory not found: {project_path}")
        raise HTTPException(status_code=404, detail="Project directory not found")

    sessions = list_sessions(project)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session_detail_route(session_id: int, project_path: str = Query(..., description="Path to the project directory")):
    """Get detailed info for a specific session."""
    from pathlib import Path

    project = Path(project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    detail = get_session_detail(project, session_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return detail


@router.delete("/sessions/{session_id}")
async def delete_session_route(session_id: int, project_path: str = Query(..., description="Path to the project directory")):
    """Delete a specific session."""
    from pathlib import Path

    project = Path(project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    deleted = delete_session_by_id(project, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {"deleted": True, "session_id": session_id}


@router.get("/learning")
async def get_learning_route(project_path: str = Query(..., description="Path to the project directory")):
    """Get learning data for a project."""
    from pathlib import Path

    project = Path(project_path)
    
    # Log for debugging path encoding issues
    logger.info(f"GET /api/learning: project_path={project_path!r}, exists={project.exists()}")
    
    if not project.exists():
        logger.warning(f"Project directory not found: {project_path}")
        raise HTTPException(status_code=404, detail="Project directory not found")

    learning = load_learning(project)

    # Convert to dict format
    return {
        "project_name": learning.project_name,
        "review_count": learning.review_count,
        "preferences": learning.preferences,
        "blind_spots": learning.blind_spots,
        "resolutions": learning.resolutions,
        "ambiguity_intentional": learning.ambiguity_intentional,
        "ambiguity_accidental": learning.ambiguity_accidental,
    }


@router.post("/learning/export")
async def export_learning_route(req: ProjectPathRequest):
    """Export LEARNING.md to the project directory."""
    from pathlib import Path

    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    filepath = export_learning_markdown(project)
    return {"exported": True, "path": str(filepath)}


@router.delete("/learning")
async def reset_learning_route(project_path: str = Query(..., description="Path to the project directory")):
    """Reset all learning data for a project."""
    from pathlib import Path

    project = Path(project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    conn = get_connection(project)
    try:
        LearningStore.reset(conn)
    finally:
        conn.close()

    return {"reset": True}


@router.delete("/learning/entries/{entry_id}")
async def delete_learning_entry_route(entry_id: int, project_path: str = Query(..., description="Path to the project directory")):
    """Delete a single learning entry."""
    from pathlib import Path

    project = Path(project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    conn = get_connection(project)
    try:
        deleted = LearningStore.remove_entry(conn, entry_id)
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Learning entry {entry_id} not found")

    return {"deleted": True, "entry_id": entry_id}
