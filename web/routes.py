"""
REST API routes for the lit-critic Web UI.
"""

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from server.config import AVAILABLE_MODELS, DEFAULT_MODEL, API_KEY_ENV_VARS
from server.session import load_session
from .session_manager import WebSessionManager

router = APIRouter(prefix="/api")

# Single shared session manager (single-user local tool)
session_mgr = WebSessionManager()


# --- Request models ---

class AnalyzeRequest(BaseModel):
    scene_path: str
    project_path: str
    api_key: Optional[str] = None
    model: Optional[str] = None


class ResumeRequest(BaseModel):
    project_path: str
    api_key: Optional[str] = None


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


# --- Helper ---

def _resolve_api_key(provided: Optional[str], model: Optional[str] = None) -> str:
    """Get API key from request or environment, based on the model's provider.

    Tries, in order:
    1. The explicitly provided key.
    2. The provider-specific env var (ANTHROPIC_API_KEY or OPENAI_API_KEY).
    3. Falls back to ANTHROPIC_API_KEY for backward compatibility.
    """
    if provided:
        return provided

    # Determine provider from model
    provider = None
    if model and model in AVAILABLE_MODELS:
        provider = AVAILABLE_MODELS[model]["provider"]

    if provider and provider in API_KEY_ENV_VARS:
        key = os.environ.get(API_KEY_ENV_VARS[provider])
        if key:
            return key

    # Backward-compatible fallback
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    env_vars = " or ".join(API_KEY_ENV_VARS.values())
    raise HTTPException(
        status_code=400,
        detail=f"No API key provided. Pass api_key in request body or set {env_vars} environment variable."
    )


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
    }


@router.post("/analyze")
async def start_analysis(req: AnalyzeRequest):
    """Start a new multi-lens analysis."""
    model = req.model or DEFAULT_MODEL
    api_key = _resolve_api_key(req.api_key, model)

    try:
        result = await session_mgr.start_analysis(req.scene_path, req.project_path, api_key, model=model)
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
    """Resume a previously saved session."""
    # Peek at the saved session to determine the model/provider for API key resolution
    saved = load_session(Path(req.project_path))
    saved_model = saved.get("model", DEFAULT_MODEL) if saved else None
    api_key = _resolve_api_key(req.api_key, saved_model)

    try:
        result = await session_mgr.resume_session(req.project_path, api_key)
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


@router.post("/finding/skip-minor")
async def skip_minor():
    """Enable skip minor and advance."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    finding = session_mgr.skip_minor_findings()
    if finding is None:
        return {"complete": True, "message": "All findings have been presented."}

    return {"complete": False, **finding}


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


@router.post("/session/save")
async def save_session_route():
    """Save the current session to disk."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.save_current_session()
    return result


@router.delete("/session")
async def clear_session():
    """Delete the saved session file."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.clear_session()
    return result


@router.post("/learning/save")
async def save_learning():
    """Save LEARNING.md to the project directory."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.save_learning()
    return result
