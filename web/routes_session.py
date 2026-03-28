"""
Active-session finding-flow routes.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .route_helpers import (
    session_mgr,
    _ensure_finding_origins_in_response,
    _ensure_mutable_session_loaded,
)
from .schemas import AmbiguityRequest, DiscussRequest, GotoRequest, RejectRequest

router = APIRouter()


@router.get("/session")
async def get_session():
    """Get current session info."""
    return _ensure_finding_origins_in_response(session_mgr.get_session_info())


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

    return _ensure_finding_origins_in_response({"complete": False, **finding})


@router.post("/finding/continue")
async def continue_finding():
    """Advance to the next finding, checking for scene changes first."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = await session_mgr.advance_with_scene_check()
    return _ensure_finding_origins_in_response(result)


@router.post("/finding/accept")
async def accept_finding():
    """Accept the current finding and advance (with scene change check)."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    result = session_mgr.accept_finding()
    next_result = await session_mgr.advance_with_scene_check()

    return _ensure_finding_origins_in_response({
        "action": result,
        "next": next_result,
    })


@router.post("/finding/reject")
async def reject_finding(req: RejectRequest):
    """Reject the current finding and advance (with scene change check)."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    result = session_mgr.reject_finding(req.reason)
    next_result = await session_mgr.advance_with_scene_check()

    return _ensure_finding_origins_in_response({
        "action": result,
        "next": next_result,
    })


@router.post("/finding/discuss")
async def discuss_finding(req: DiscussRequest):
    """Send a discussion message about the current finding."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    result = await session_mgr.discuss(req.message)
    return _ensure_finding_origins_in_response(result)


@router.post("/finding/discuss/stream")
async def discuss_finding_stream(req: DiscussRequest):
    """Stream discussion response token-by-token via SSE.

    Emits SSE events:
        {"type": "token", "text": "..."} — streaming text chunk
        {"type": "done", ...}            — final result (same shape as /finding/discuss response)
    """
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    async def event_stream():
        async for chunk_type, data in session_mgr.discuss_stream(req.message):
            if chunk_type == "scene_change":
                normalized_data = _ensure_finding_origins_in_response(data)
                yield f"data: {json.dumps({'type': 'scene_change', **normalized_data})}\n\n"
            elif chunk_type == "token":
                yield f"data: {json.dumps({'type': 'token', 'text': data})}\n\n"
            elif chunk_type == "done":
                normalized_data = _ensure_finding_origins_in_response(data)
                yield f"data: {json.dumps({'type': 'done', **normalized_data})}\n\n"

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
    return _ensure_finding_origins_in_response(result)


@router.post("/finding/ambiguity")
async def mark_ambiguity(req: AmbiguityRequest):
    """Mark current finding's ambiguity as intentional or accidental."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    result = session_mgr.mark_ambiguity(req.intentional)
    return result


@router.post("/finding/review")
async def review_finding():
    """Re-check the current finding against scene edits."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")
    _ensure_mutable_session_loaded()

    return _ensure_finding_origins_in_response(await session_mgr.review_current_finding())


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

    return _ensure_finding_origins_in_response({"complete": False, **finding})
