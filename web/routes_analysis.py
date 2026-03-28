"""
Analysis, session-lifecycle, and audit routes.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from lit_platform.services import (
    audit_scene,
    audit_indexes_deterministic,
    audit_indexes_semantic,
    format_audit_report,
    check_active_session,
    generate_and_save_session_summary,
    get_session_detail,
    scan_scene_for_index_entries,
    format_index_report,
)
from lit_platform.services.analysis_service import DEFAULT_MODEL, resolve_model
from lit_platform.runtime.model_slots import resolve_models_for_mode
from lit_platform.user_config import get_model_slots
from lit_platform.services.project_knowledge_service import ensure_project_knowledge_fresh
from .route_helpers import (
    MODE_COST_HINTS,
    session_mgr,
    _build_tier_cost_summary,
    _ensure_finding_origins_in_response,
    _ensure_repo_preflight_ready,
    _normalise_model_name,
    _normalise_optional_model_name,
    _resolve_analysis_and_discussion_keys,
    _resolve_provider_api_key,
)
from .session_manager import ResumeScenePathError
from .schemas import (
    AnalyzeRequest,
    CheckSessionRequest,
    IndexAuditRequest,
    IndexRequest,
    RerunAnalyzeRequest,
    ResumeRequest,
    ResumeSessionByIdRequest,
    SceneAuditRequest,
    ViewSessionRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze")
async def start_analysis(req: AnalyzeRequest):
    """Start a new multi-lens analysis."""
    _ensure_repo_preflight_ready()
    project = Path(req.project_path)
    if project.exists():
        knowledge_refresh = ensure_project_knowledge_fresh(project)
    else:
        knowledge_refresh = {
            "refreshed": False,
            "stale_scenes": [],
            "stale_indexes": [],
            "reason": "project_missing",
        }

    mode = (req.mode or "deep").strip().lower()
    if mode not in {"quick", "deep"}:
        raise HTTPException(status_code=400, detail="mode must be one of: quick, deep")

    selected_scene_paths = req.scene_paths or ([req.scene_path] if req.scene_path else [])
    if not selected_scene_paths:
        raise HTTPException(status_code=400, detail="scene_path or scene_paths is required")

    if req.model is not None or req.discussion_model is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Deprecated fields are not supported for /api/analyze: model, discussion_model. "
                "Use mode with configured model slots."
            ),
        )

    resolved = resolve_models_for_mode(mode, get_model_slots())
    model = _normalise_model_name(resolved["analysis_model"])
    discussion_model = _normalise_optional_model_name(resolved["discussion_model"])

    analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
        model,
        discussion_model,
        req.api_key,
        req.discussion_api_key,
    )

    try:
        result = await session_mgr.start_analysis(
            selected_scene_paths[0],
            req.project_path,
            analysis_key,
            model=model,
            discussion_model=discussion_model,
            discussion_api_key=discussion_key,
            scene_paths=selected_scene_paths,
            depth_mode=mode,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    result["mode_cost_hint"] = MODE_COST_HINTS.get(mode, MODE_COST_HINTS["deep"])
    result["tier_cost_summary"] = _build_tier_cost_summary(
        mode=mode,
        checker_model=model,
        frontier_model=discussion_model,
    )
    result["knowledge_refresh"] = knowledge_refresh

    return _ensure_finding_origins_in_response(result)


@router.post("/analyze/rerun")
async def rerun_analysis(req: RerunAnalyzeRequest):
    """Re-run analysis for the active session's scene set with current settings."""
    _ensure_repo_preflight_ready()

    if not session_mgr.state:
        raise HTTPException(status_code=404, detail="No active session")

    model = _normalise_model_name(session_mgr.state.model)
    discussion_model = _normalise_optional_model_name(session_mgr.state.discussion_model)

    analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
        model,
        discussion_model,
        req.api_key,
        req.discussion_api_key,
    )

    scene_paths = session_mgr.state.scene_paths or [session_mgr.state.scene_path]
    depth_mode = getattr(session_mgr.state, "depth_mode", "deep") or "deep"
    try:
        result = await session_mgr.start_analysis(
            scene_paths[0],
            req.project_path,
            analysis_key,
            model=model,
            discussion_model=discussion_model,
            discussion_api_key=discussion_key,
            scene_paths=scene_paths,
            depth_mode=depth_mode,
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
            scene_path_overrides=req.scene_path_overrides,
        )
    except ResumeScenePathError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scene_path_not_found",
                "message": str(e),
                "saved_scene_path": e.saved_scene_path,
                "attempted_scene_path": e.attempted_scene_path,
                "saved_scene_paths": e.saved_scene_paths,
                "missing_scene_paths": e.missing_scene_paths,
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

    return _ensure_finding_origins_in_response(result)


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
            scene_path_overrides=req.scene_path_overrides,
        )
    except ResumeScenePathError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scene_path_not_found",
                "message": str(e),
                "saved_scene_path": e.saved_scene_path,
                "attempted_scene_path": e.attempted_scene_path,
                "saved_scene_paths": e.saved_scene_paths,
                "missing_scene_paths": e.missing_scene_paths,
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

    return _ensure_finding_origins_in_response(result)


@router.post("/view-session")
async def view_session(req: ViewSessionRequest):
    """Load any session (active, completed, or abandoned) for viewing/interaction."""
    _ensure_repo_preflight_ready()

    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    detail = get_session_detail(project, req.session_id, passive=True)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

    status = detail.get("status", "active")
    passive_view = not req.reopen

    saved_model = _normalise_model_name(detail.get("model"), default=DEFAULT_MODEL)
    saved_discussion_model = _normalise_optional_model_name(detail.get("discussion_model"))

    analysis_key, discussion_key = _resolve_analysis_and_discussion_keys(
        saved_model,
        saved_discussion_model,
        req.api_key,
        req.discussion_api_key,
    )

    try:
        result = await session_mgr.load_session_for_viewing(
            req.project_path,
            req.session_id,
            analysis_key,
            discussion_api_key=discussion_key,
            scene_path_override=req.scene_path_override,
            scene_path_overrides=req.scene_path_overrides,
            passive=passive_view,
            reopen=req.reopen,
        )
    except ResumeScenePathError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scene_path_not_found",
                "message": str(e),
                "saved_scene_path": e.saved_scene_path,
                "attempted_scene_path": e.attempted_scene_path,
                "saved_scene_paths": e.saved_scene_paths,
                "missing_scene_paths": e.missing_scene_paths,
                "project_path": e.project_path,
                "override_provided": e.override_provided,
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _ensure_finding_origins_in_response(result)


@router.post("/check-session")
async def check_saved_session(req: CheckSessionRequest):
    """Check if a saved session exists for the given project."""
    return session_mgr.check_saved_session(req.project_path)


@router.post("/index")
async def index_scene(req: IndexRequest):
    """Deprecated: scan a scene and insert new entries into index files.

    Returns a structured report of what was added to each file.
    """
    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    scene_path = Path(req.scene_path)
    if not scene_path.exists():
        raise HTTPException(status_code=404, detail="Scene file not found")

    model = _normalise_model_name(req.model)
    provider = resolve_model(model)["provider"]
    api_key = _resolve_provider_api_key(provider, req.api_key, "api_key")

    # Load scene
    try:
        scene_content = scene_path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read scene file: {e}") from e

    # Load index files (read-only snapshot for LLM context)
    # Use PlatformFacade directly to avoid CLI print() side-effects
    from lit_platform.facade import PlatformFacade
    from lit_platform.services.analysis_service import OPTIONAL_FILES
    indexes = PlatformFacade.load_legacy_indexes_from_project(
        project, optional_filenames=tuple(OPTIONAL_FILES)
    )

    # Create a lightweight LLM client
    from lit_platform.runtime.llm import create_client as _create_llm_client
    client = _create_llm_client(provider, api_key)

    model_cfg = resolve_model(model)

    try:
        report = await scan_scene_for_index_entries(
            scene_content=scene_content,
            project_path=project,
            indexes=indexes,
            client=client,
            model=model_cfg["id"],
            max_tokens=model_cfg["max_tokens"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "report": report,
        "summary": format_index_report(report),
        "deprecated": True,
        "replacement": "/api/knowledge/refresh",
    }


@router.post("/audit")
async def audit_indexes(req: IndexAuditRequest):
    """Deprecated: run deterministic/deep index audit and return findings."""
    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    from lit_platform.facade import PlatformFacade
    from lit_platform.services.analysis_service import OPTIONAL_FILES

    indexes = PlatformFacade.load_legacy_indexes_from_project(
        project,
        optional_filenames=tuple(OPTIONAL_FILES),
    )
    report = audit_indexes_deterministic(indexes)

    deep_error: Optional[str] = None
    resolved_model = _normalise_model_name(req.model)

    if req.deep:
        model_cfg = resolve_model(resolved_model)
        provider = model_cfg["provider"]
        try:
            api_key = _resolve_provider_api_key(provider, req.api_key, "api_key")
            from lit_platform.runtime.llm import create_client as _create_llm_client

            client = _create_llm_client(provider, api_key)
            report.semantic = await audit_indexes_semantic(
                indexes,
                client,
                model=model_cfg["id"],
                max_tokens=model_cfg["max_tokens"],
            )
        except Exception as e:
            logger.warning("Deep index audit failed: %s", e)
            deep_error = str(e)

    return {
        "deterministic": [f.__dict__ for f in report.deterministic],
        "semantic": [f.__dict__ for f in report.semantic],
        "placeholder_census": report.placeholder_census,
        "formatted_report": format_audit_report(report),
        "deep": req.deep,
        "model": resolved_model,
        "deep_error": deep_error,
        "deprecated": True,
        "replacement": "/api/knowledge/refresh",
    }


@router.post("/scenes/audit")
async def audit_scene_route(req: SceneAuditRequest):
    """Deprecated: run deterministic/deep scene audit and return findings."""
    project = Path(req.project_path)
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    scene_path = Path(req.scene_path)
    if not scene_path.exists():
        raise HTTPException(status_code=404, detail="Scene file not found")

    try:
        scene_content = scene_path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read scene file: {e}") from e

    from lit_platform.facade import PlatformFacade
    from lit_platform.services.analysis_service import OPTIONAL_FILES

    indexes = PlatformFacade.load_legacy_indexes_from_project(
        project,
        optional_filenames=tuple(OPTIONAL_FILES),
    )

    deep_error: Optional[str] = None
    resolved_model = _normalise_model_name(req.model)
    model_cfg = resolve_model(resolved_model)
    model_id = model_cfg["id"]
    max_tokens = model_cfg["max_tokens"]
    client = None

    if req.deep:
        provider = model_cfg["provider"]
        try:
            api_key = _resolve_provider_api_key(provider, req.api_key, "api_key")
            from lit_platform.runtime.llm import create_client as _create_llm_client

            client = _create_llm_client(provider, api_key)
        except Exception as e:
            logger.warning("Deep scene audit setup failed: %s", e)
            deep_error = str(e)

    result = await audit_scene(
        scene_content,
        indexes,
        deep=req.deep,
        client=client,
        model=model_id,
        max_tokens=max_tokens,
    )

    if deep_error and not result.get("deep_error"):
        result["deep_error"] = deep_error

    return {
        "deterministic": [f.__dict__ for f in result["deterministic"]],
        "semantic": [f.__dict__ for f in result["semantic"]],
        "deep": req.deep,
        "model": resolved_model,
        "deep_error": result.get("deep_error"),
        "deprecated": True,
        "replacement": "/api/knowledge/refresh",
    }


@router.post("/learning/save")
async def save_learning():
    """Export LEARNING.md to the project directory."""
    if not session_mgr.is_active:
        raise HTTPException(status_code=404, detail="No active session")

    result = session_mgr.save_learning()
    return result


@router.post("/session/summary")
async def generate_session_summary():
    """Generate and return the session-end disconfirming meta-observation.

    Called by the frontend after all findings reach terminal status.  The
    summary is generated using the discussion model, stored on the session
    record, and returned to the caller for display.
    """
    if not session_mgr.is_active or not session_mgr.state:
        raise HTTPException(status_code=404, detail="No active session")

    try:
        summary = await generate_and_save_session_summary(session_mgr.state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {"summary": summary or ""}
