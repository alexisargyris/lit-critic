"""
Server-side session manager for the Web UI.

Bridges the web layer to existing lit-critic modules.
All mutations are auto-saved to SQLite — no explicit save step needed.
"""

import asyncio
from pathlib import Path
from typing import Optional

from lit_platform.facade import PlatformFacade
from lit_platform.models import SessionState, Finding, LearningData, LensResult, CoordinatorError
from lit_platform.persistence import SessionStore, FindingStore
from lit_platform.runtime.utils import (
    concatenate_scenes,
    map_global_range_to_scene,
    remap_location_line_range,
)
from lit_platform.services.analysis_service import (
    DEFAULT_MODEL,
    INDEX_FILES,
    OPTIONAL_FILES,
    create_client,
    is_known_model,
    normalize_lens_preferences,
    resolve_model,
    run_coordinator,
    run_coordinator_chunked,
    run_lens,
)
from lit_platform.persistence import LearningStore

from lit_platform.services import (
    load_learning,
    load_learning_from_db,
    compute_index_context_hash,
    detect_index_context_changes,
    generate_learning_markdown,
    export_learning_markdown,
    check_active_session,
    load_active_session,
    validate_session,
    load_session_by_id,
    create_session,
    complete_session,
    abandon_active_session,
    complete_active_session,
    detect_and_apply_scene_changes,
    review_current_finding_against_scene_edits,
    persist_finding,
    persist_session_index,
    persist_session_learning,
    persist_discussion_history,
    discuss_finding,
    discuss_finding_stream,
)
from lit_platform.session_state_machine import (
    apply_acceptance,
    apply_discussion_status,
    apply_rejection,
    first_unresolved_index,
    next_available_index,
    next_index_for_lens,
    record_ambiguity_answer,
    restore_learning_session,
)

# Backward-compatible names used by existing tests/mocks.
handle_discussion = discuss_finding
handle_discussion_stream = discuss_finding_stream


class AnalysisProgress:
    """Tracks progress of the multi-lens analysis for SSE streaming."""

    def __init__(self):
        self.events: list[dict] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self.complete = False
        self.error: Optional[str] = None

    def add_event(self, event_type: str, data: dict):
        event = {"type": event_type, **data}
        self.events.append(event)
        self._queue.put_nowait(event)

    async def get_event(self) -> dict:
        return await self._queue.get()


class WebSessionManager:
    """Manages a single review session for the web UI."""

    def __init__(self):
        self.state: Optional[SessionState] = None
        self.results: Optional[dict] = None
        self.current_index: int = 0
        self.analysis_progress: Optional[AnalysisProgress] = None

    @property
    def is_active(self) -> bool:
        return self.state is not None and self.state.findings

    @property
    def total_findings(self) -> int:
        if not self.state or not self.state.findings:
            return 0
        return len(self.state.findings)

    def _load_project_files(self, project_path: Path) -> dict[str, str]:
        """Load all index files from the project directory via Platform layer."""
        loaded = []
        missing = []

        indexes = PlatformFacade.load_legacy_indexes_from_project(
            project_path,
            optional_filenames=tuple(OPTIONAL_FILES),
        )

        for filename in INDEX_FILES:
            if indexes.get(filename):
                loaded.append(filename)
            else:
                missing.append(filename)

        for filename in OPTIONAL_FILES:
            if indexes.get(filename):
                loaded.append(filename)

        return indexes, loaded, missing

    def _load_scene(self, scene_path: Path) -> str:
        """Load the scene file via Platform layer."""
        if not scene_path.exists():
            raise FileNotFoundError(f"Scene file not found: {scene_path}")
        return PlatformFacade.load_scene_text(scene_path)

    def _load_scenes(self, scene_paths: list[Path]) -> tuple[str, list[dict]]:
        """Load and concatenate scenes into analysis text and line map."""
        scene_docs = [(str(scene), self._load_scene(scene)) for scene in scene_paths]
        return concatenate_scenes(scene_docs)

    @staticmethod
    def _extract_saved_scene_paths(session_data: dict) -> list[str]:
        """Extract persisted scene paths from session payload in normalized order."""
        scene_paths = [str(p) for p in (session_data.get("scene_paths") or []) if p]
        if scene_paths:
            return scene_paths

        single = session_data.get("scene_path", "")
        return [single] if single else []

    @staticmethod
    def _normalize_scene_path_overrides(
        scene_path_overrides: dict[str, str] | None,
    ) -> dict[str, str]:
        """Normalize scene path override mapping payload."""
        if not scene_path_overrides:
            return {}

        normalized: dict[str, str] = {}
        for old_path, new_path in scene_path_overrides.items():
            if not old_path or not new_path:
                continue
            normalized[str(old_path)] = str(new_path)
        return normalized

    def _resolve_session_scene_paths(
        self,
        saved_scene_paths: list[str],
        scene_path_override: str | None,
        scene_path_overrides: dict[str, str] | None,
    ) -> tuple[list[str], dict[str, str], list[str], bool]:
        """Resolve saved scene paths using optional single/map overrides.

        Returns:
            resolved_scene_paths,
            remap(old_path->new_path),
            missing_resolved_paths,
            override_provided
        """
        overrides_map = self._normalize_scene_path_overrides(scene_path_overrides)
        override_provided = bool(scene_path_override) or bool(overrides_map)

        resolved_scene_paths = list(saved_scene_paths)
        remap: dict[str, str] = {}

        # Apply explicit per-path overrides first.
        for i, saved_path in enumerate(saved_scene_paths):
            mapped = overrides_map.get(saved_path)
            if mapped:
                resolved_scene_paths[i] = mapped
                remap[saved_path] = mapped

        # Backward-compatible single override: apply to first missing saved path
        # (or primary path when nothing is missing yet).
        if scene_path_override and not overrides_map:
            missing_saved = [p for p in saved_scene_paths if not Path(p).exists()]
            target_old = missing_saved[0] if missing_saved else saved_scene_paths[0]
            target_idx = saved_scene_paths.index(target_old)
            resolved_scene_paths[target_idx] = scene_path_override
            remap[target_old] = scene_path_override

        missing_resolved_paths = [p for p in resolved_scene_paths if not Path(p).exists()]
        return resolved_scene_paths, remap, missing_resolved_paths, override_provided

    async def start_analysis(self, scene_path: str, project_path: str, api_key: str,
                             model: str = DEFAULT_MODEL, discussion_model: str = None,
                             discussion_api_key: str | None = None,
                             scene_paths: list[str] | None = None,
                             lens_preferences: dict | None = None) -> dict:
        """Start a new analysis. Returns summary info. Populates self.state."""
        project = Path(project_path)
        requested_scene_paths = scene_paths or [scene_path]
        scenes = [Path(p) for p in requested_scene_paths]

        if not project.exists():
            raise FileNotFoundError(f"Project directory not found: {project}")

        # Validate model
        if not is_known_model(model):
            model = DEFAULT_MODEL

        # Validate discussion model
        if discussion_model and not is_known_model(discussion_model):
            discussion_model = None

        # Handle existing active session
        active = check_active_session(project)
        if active.get("exists"):
            # Auto-complete the previous session
            complete_active_session(project)

        # Load files
        indexes, loaded_files, missing_files = self._load_project_files(project)
        scene_content, scene_line_map = self._load_scenes(scenes)

        # Load learning and inject directly into indexes so that analysis prompts
        # always reflect the current DB state (no need for a LEARNING.md file on disk).
        learning = load_learning(project)
        indexes['LEARNING.md'] = generate_learning_markdown(learning)

        # Initialize provider-agnostic client
        provider = resolve_model(model)["provider"]
        client = create_client(provider, api_key)

        # Initialize discussion client if using different model
        discussion_client = None
        if discussion_model:
            discussion_provider = resolve_model(discussion_model)["provider"]
            # Only create a new client if the provider differs
            if discussion_provider != provider:
                discussion_client = create_client(discussion_provider, discussion_api_key or api_key)
            else:
                # Same provider — reuse the same client
                discussion_client = client

        # Create session state
        self.state = SessionState(
            client=client,
            scene_content=scene_content,
            scene_path=str(scenes[0]),
            project_path=project,
            indexes=indexes,
            scene_paths=[str(s) for s in scenes],
            scene_line_map=scene_line_map,
            learning=learning,
            lens_preferences=normalize_lens_preferences(lens_preferences),
            model=model,
            discussion_model=discussion_model,
            discussion_client=discussion_client,
            index_context_hash=compute_index_context_hash(indexes),
            index_context_stale=False,
            index_rerun_prompted=False,
            index_changed_files=[],
        )

        # Set up progress tracking
        self.analysis_progress = AnalysisProgress()

        # Run analysis with progress tracking
        self.analysis_progress.add_event("status", {"message": "Running 6 lenses in parallel..."})

        model_id = self.state.model_id
        max_tokens = self.state.model_max_tokens

        lens_names = ["prose", "structure", "logic", "clarity", "continuity", "dialogue"]
        lens_tasks = [
            self._run_lens_with_progress(client, name, scene_content, indexes,
                                         model=model_id, max_tokens=max_tokens)
            for name in lens_names
        ]

        lens_results = await asyncio.gather(*lens_tasks)

        # Check for errors
        for result in lens_results:
            if result.error:
                self.analysis_progress.add_event("warning", {
                    "lens": result.lens_name,
                    "message": f"{result.lens_name} lens failed: {result.error}"
                })

        # Coordinate (chunked: prose -> structure -> coherence)
        self.analysis_progress.add_event("status", {"message": "Coordinating results (chunked)..."})

        def _coord_progress(event_type: str, data: dict):
            self.analysis_progress.add_event(event_type, data)

        try:
            coordinated = await run_coordinator_chunked(
                client, lens_results, scene_content,
                model=model_id, max_tokens=max_tokens,
                progress_callback=_coord_progress,
                lens_preferences=self.state.lens_preferences,
            )
        except CoordinatorError:
            # Fallback to single-call coordinator
            self.analysis_progress.add_event("warning", {
                "message": "Chunked coordinator failed. Falling back to single-call..."
            })
            try:
                coordinated = await run_coordinator(
                    client, lens_results, scene_content,
                    model=model_id, max_tokens=max_tokens,
                    lens_preferences=self.state.lens_preferences,
                )
            except CoordinatorError as e:
                error_msg = str(e)
                self.analysis_progress.add_event("error", {"message": f"Coordination error: {error_msg}"})
                self.analysis_progress.complete = True
                self.analysis_progress.error = error_msg
                return {"error": error_msg}

        self.results = coordinated

        # Convert findings to Finding objects
        findings_data = coordinated.get("findings", [])
        self.state.findings = [
            Finding(
                number=f.get('number', i + 1),
                severity=f.get('severity', 'minor'),
                lens=f.get('lens', 'unknown'),
                location=f.get('location', ''),
                line_start=f.get('line_start'),
                line_end=f.get('line_end'),
                evidence=f.get('evidence', ''),
                impact=f.get('impact', ''),
                options=f.get('options', []),
                flagged_by=f.get('flagged_by', []),
                ambiguity_type=f.get('ambiguity_type')
            )
            for i, f in enumerate(findings_data)
        ]

        for finding in self.state.findings:
            mapped_scene_path, local_start, local_end = map_global_range_to_scene(
                self.state.scene_line_map,
                finding.line_start,
                finding.line_end,
            )
            finding.scene_path = mapped_scene_path or self.state.scene_path
            finding.line_start = local_start
            finding.line_end = local_end
            finding.location = remap_location_line_range(
                finding.location,
                finding.line_start,
                finding.line_end,
            )
        self.state.glossary_issues = coordinated.get("glossary_issues", [])
        self.current_index = 0

        # Auto-save: create session in DB
        create_session(self.state, self.state.glossary_issues)

        self.analysis_progress.add_event("complete", {
            "message": "Analysis complete",
            "total_findings": len(self.state.findings)
        })
        self.analysis_progress.complete = True

        return self._build_summary()

    async def _run_lens_with_progress(self, client, lens_name, scene, indexes,
                                      model=None, max_tokens=None):
        """Run a single lens and emit progress event on completion."""
        kwargs = {}
        if model is not None:
            kwargs["model"] = model
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        result = await run_lens(client, lens_name, scene, indexes, **kwargs)
        if result.error:
            self.analysis_progress.add_event("lens_error", {
                "lens": lens_name,
                "message": result.error
            })
        else:
            self.analysis_progress.add_event("lens_complete", {
                "lens": lens_name
            })
        return result

    async def resume_session(self, project_path: str, api_key: str | None,
                             discussion_api_key: str | None = None,
                             scene_path_override: str | None = None,
                             scene_path_overrides: dict[str, str] | None = None) -> dict:
        """Resume a saved session. Returns summary info."""
        project = Path(project_path)

        session_data = load_active_session(project)
        if not session_data:
            raise FileNotFoundError("No active session found in project directory.")

        # Extract the DB connection (caller takes ownership)
        conn = session_data.pop("_conn")

        return await self._load_session_into_state(
            project,
            session_data,
            conn,
            api_key,
            discussion_api_key=discussion_api_key,
            scene_path_override=scene_path_override,
            scene_path_overrides=scene_path_overrides,
        )

    async def resume_session_by_id(
        self,
        project_path: str,
        session_id: int,
        api_key: str | None,
        discussion_api_key: str | None = None,
        scene_path_override: str | None = None,
        scene_path_overrides: dict[str, str] | None = None,
    ) -> dict:
        """Resume a specific saved session by id. Returns summary info."""
        project = Path(project_path)

        session_data = load_session_by_id(project, session_id)
        if not session_data:
            raise FileNotFoundError(f"Session {session_id} not found in project directory.")

        status = session_data.get("status", "active")
        if status != "active":
            conn = session_data.get("_conn")
            if conn:
                conn.close()
            raise ValueError(
                f"Session {session_id} is '{status}' and cannot be resumed. "
                "Only active sessions can be resumed."
            )

        # Extract the DB connection (caller takes ownership)
        conn = session_data.pop("_conn")

        return await self._load_session_into_state(
            project,
            session_data,
            conn,
            api_key,
            discussion_api_key=discussion_api_key,
            scene_path_override=scene_path_override,
            scene_path_overrides=scene_path_overrides,
        )

    async def load_session_for_viewing(
        self,
        project_path: str,
        session_id: int,
        api_key: str | None,
        discussion_api_key: str | None = None,
        scene_path_override: str | None = None,
        scene_path_overrides: dict[str, str] | None = None,
    ) -> dict:
        """Load any session (active, completed, or abandoned) for viewing/interactions."""
        project = Path(project_path)

        session_data = load_session_by_id(project, session_id)
        if not session_data:
            raise FileNotFoundError(f"Session {session_id} not found in project directory.")

        conn = session_data.pop("_conn")

        return await self._load_session_into_state(
            project,
            session_data,
            conn,
            api_key,
            discussion_api_key=discussion_api_key,
            scene_path_override=scene_path_override,
            scene_path_overrides=scene_path_overrides,
        )

    async def _load_session_into_state(
        self,
        project: Path,
        session_data: dict,
        conn,
        api_key: str | None,
        discussion_api_key: str | None = None,
        scene_path_override: str | None = None,
        scene_path_overrides: dict[str, str] | None = None,
    ) -> dict:
        """Shared logic for loading a persisted session into manager state."""

        saved_scene_paths = self._extract_saved_scene_paths(session_data)
        if not saved_scene_paths:
            conn.close()
            raise ValueError("Session data is corrupted (missing scene path)")

        resolved_scene_paths, remap, missing_scene_paths, override_provided = self._resolve_session_scene_paths(
            saved_scene_paths,
            scene_path_override,
            scene_path_overrides,
        )

        if missing_scene_paths:
            conn.close()
            saved_scene_path = saved_scene_paths[0]
            attempted_scene_path = missing_scene_paths[0]

            raise ResumeScenePathError(
                (
                    "Provided scene file path(s) do not resolve all session scenes."
                    if override_provided
                    else "Saved scene file was not found. The session may have been moved from another machine."
                ),
                saved_scene_path=str(saved_scene_path),
                attempted_scene_path=str(attempted_scene_path),
                project_path=str(project),
                override_provided=override_provided,
                saved_scene_paths=[str(p) for p in saved_scene_paths],
                missing_scene_paths=[str(p) for p in missing_scene_paths],
            )

        if remap:
            SessionStore.update_scene_paths(conn, session_data["session_id"], [str(p) for p in resolved_scene_paths])
            FindingStore.remap_scene_paths(conn, session_data["session_id"], remap)
            session_data["scene_paths"] = [str(p) for p in resolved_scene_paths]
            session_data["scene_path"] = str(resolved_scene_paths[0])

        # Load files
        indexes, loaded_files, missing_files = self._load_project_files(project)
        scene_content, scene_line_map = self._load_scenes([Path(p) for p in resolved_scene_paths])
        scene_path = str(resolved_scene_paths[0])

        # Validate (warn but don't block — scene changes will be detected)
        is_valid, error_msg = validate_session(
            session_data,
            scene_content,
            scene_path,
            [str(p) for p in resolved_scene_paths],
        )

        # Load learning from DB
        learning = load_learning_from_db(conn)
        restore_learning_session(learning, session_data.get("learning_session", {}))

        # Restore model from session
        saved_model = session_data.get("model", DEFAULT_MODEL)
        if not is_known_model(saved_model):
            saved_model = DEFAULT_MODEL

        # Restore discussion model from session
        saved_discussion_model = session_data.get("discussion_model")
        if saved_discussion_model and not is_known_model(saved_discussion_model):
            saved_discussion_model = None

        # Initialize provider-agnostic client
        provider = resolve_model(saved_model)["provider"]
        client = create_client(provider, api_key)

        # Initialize discussion client if using different model
        discussion_client = None
        if saved_discussion_model:
            discussion_provider = resolve_model(saved_discussion_model)["provider"]
            # Only create a new client if the provider differs
            if discussion_provider != provider:
                discussion_client = create_client(discussion_provider, discussion_api_key or api_key)
            else:
                # Same provider — reuse the same client
                discussion_client = client

        # Create session state
        self.state = SessionState(
            client=client,
            scene_content=scene_content,
            scene_path=scene_path,
            project_path=project,
            indexes=indexes,
            scene_paths=[str(p) for p in resolved_scene_paths],
            scene_line_map=scene_line_map,
            learning=learning,
            findings=[Finding.from_dict(f) for f in session_data.get("findings", [])],
            glossary_issues=session_data.get("glossary_issues", []),
            discussion_history=session_data.get("discussion_history", []),
            lens_preferences=session_data.get("lens_preferences") or normalize_lens_preferences(None),
            model=saved_model,
            discussion_model=saved_discussion_model,
            discussion_client=discussion_client,
            index_context_hash=session_data.get("index_context_hash", ""),
            index_context_stale=session_data.get("index_context_stale", False),
            index_rerun_prompted=session_data.get("index_rerun_prompted", False),
            index_changed_files=session_data.get("index_changed_files", []),
            db_conn=conn,
            session_id=session_data["session_id"],
        )

        self.current_index = session_data.get("current_index", 0)

        return self._build_summary()

    def _build_summary(self) -> dict:
        """Build the summary response dict."""
        if not self.state:
            return {}

        summary = {
            "scene_path": self.state.scene_path,
            "scene_paths": self.state.scene_paths or [self.state.scene_path],
            "scene_name": Path(self.state.scene_path).name,
            "project_path": str(self.state.project_path),
            "total_findings": len(self.state.findings),
            "current_index": self.current_index,
            "glossary_issues": self.state.glossary_issues,
            "counts": {"critical": 0, "major": 0, "minor": 0},
            "lens_counts": {},
            "lens_preferences": self.state.lens_preferences,
        }

        for f in self.state.findings:
            sev = f.severity.lower()
            if sev in summary["counts"]:
                summary["counts"][sev] += 1
            lens = f.lens.lower()
            if lens not in summary["lens_counts"]:
                summary["lens_counts"][lens] = {"critical": 0, "major": 0, "minor": 0}
            if sev in summary["lens_counts"][lens]:
                summary["lens_counts"][lens][sev] += 1

        # Model info
        summary["model"] = {
            "name": self.state.model,
            "id": self.state.model_id,
            "label": self.state.model_label,
        }

        # Discussion model info (if set)
        if self.state.discussion_model:
            summary["discussion_model"] = {
                "name": self.state.discussion_model,
                "id": self.state.discussion_model_id,
                "label": self.state.discussion_model_label,
            }
        else:
            summary["discussion_model"] = None

        # Learning info
        summary["learning"] = {
            "review_count": self.state.learning.review_count,
            "preferences": len(self.state.learning.preferences),
            "blind_spots": len(self.state.learning.blind_spots),
        }

        # Session ID
        if self.state.session_id:
            summary["session_id"] = self.state.session_id

        summary["index_context_stale"] = self.state.index_context_stale
        summary["index_changed_files"] = self.state.index_changed_files
        summary["rerun_recommended"] = self.state.index_context_stale
        summary["index_change"] = {
            "changed": self.state.index_context_stale,
            "stale": self.state.index_context_stale,
            "changed_files": self.state.index_changed_files,
            "prompt": False,
        }

        # Include findings_status for direct population of findings tree in VS Code extension
        # This eliminates the need for a fragile second HTTP call to GET /api/session
        summary["findings_status"] = [
            {
                "number": f.number,
                "severity": f.severity,
                "lens": f.lens,
                "status": f.status,
                "location": f.location,
                "evidence": f.evidence,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "scene_path": f.scene_path,
            }
            for f in self.state.findings
        ]

        return summary

    async def check_scene_changes(self) -> Optional[dict]:
        """Check for scene file changes and apply line adjustments + re-evaluation."""
        if not self.state:
            return None
        return await detect_and_apply_scene_changes(self.state, self.current_index)

    async def check_index_changes(self) -> Optional[dict]:
        """Check for index-context changes and apply stale/prompt semantics."""
        if not self.state:
            return None
        return detect_index_context_changes(self.state)

    def get_current_finding(self) -> Optional[dict]:
        """Get the current finding."""
        if not self.state or not self.state.findings:
            return None

        self.current_index = next_available_index(self.state.findings, self.current_index)
        if self.current_index < len(self.state.findings):
            finding = self.state.findings[self.current_index]
            return {
                "finding": finding.to_dict(include_state=True),
                "index": self.current_index,
                "current": self.current_index + 1,
                "total": len(self.state.findings),
                "is_ambiguity": finding.ambiguity_type == 'ambiguous_possibly_intentional',
            }

        return None  # All findings processed

    async def advance_with_scene_check(self) -> dict:
        """Move to next finding, checking for scene changes first."""
        self.current_index += 1
        persist_session_index(self.state, self.current_index)
        change_report = await self.check_scene_changes()
        index_change = await self.check_index_changes()
        finding = self.get_current_finding()

        result = {"scene_change": change_report, "index_change": index_change}
        if finding is None:
            if complete_session(self.state):
                # Increment review_count once per completed session.
                if self.state.db_conn:
                    LearningStore.increment_review_count(self.state.db_conn)
                    self.state.learning.review_count += 1
                result["complete"] = True
                result["message"] = "All findings have been considered."
            else:
                unresolved = self._jump_to_first_unresolved_finding()
                if unresolved is None:
                    result["complete"] = True
                    result["message"] = "No available finding, but session is not yet complete."
                else:
                    result["complete"] = False
                    result["message"] = "There are still pending findings to review."
                    result.update(unresolved)
        else:
            result["complete"] = False
            result.update(finding)

        return result

    def _jump_to_first_unresolved_finding(self) -> Optional[dict]:
        """Jump to first unresolved finding (non-terminal status), if any."""
        if not self.state:
            return None

        unresolved_index = first_unresolved_index(self.state.findings)
        if unresolved_index is None:
            return None

        self.current_index = unresolved_index

        persist_session_index(self.state, self.current_index)
        return self.get_current_finding()

    def advance(self) -> Optional[dict]:
        """Move to next finding and return it (sync, no scene check)."""
        if not self.state:
            return None
        self.current_index += 1
        persist_session_index(self.state, self.current_index)
        return self.get_current_finding()

    async def review_current_finding(self) -> dict:
        """Review only the current finding against scene edits."""
        if not self.state:
            return {"error": "No active session"}

        review = await review_current_finding_against_scene_edits(
            self.state,
            self.current_index,
        )
        index_change = await self.check_index_changes()
        finding = self.get_current_finding()

        if finding is None:
            # Keep completion semantics aligned with advance_with_scene_check().
            # A missing current finding does not always mean the session is
            # complete — there may still be unresolved findings earlier in the
            # list (e.g. after withdrawn/skipped items near the end).
            if complete_session(self.state):
                return {
                    "complete": True,
                    "message": "All findings have been considered.",
                    "review": review,
                    "index_change": index_change,
                }

            unresolved = self._jump_to_first_unresolved_finding()
            if unresolved is None:
                return {
                    "complete": True,
                    "message": "No available finding, but session is not yet complete.",
                    "review": review,
                    "index_change": index_change,
                }

            return {
                "complete": False,
                "message": "There are still pending findings to review.",
                "review": review,
                "index_change": index_change,
                **unresolved,
            }

        return {
            "complete": False,
            "review": review,
            "index_change": index_change,
            **finding,
        }

    def goto_finding(self, index: int) -> Optional[dict]:
        """Jump to a specific finding by index.

        API behavior cleanup:
        - Any in-range finding is navigable, including terminal findings
          such as ``withdrawn``.
        - Returned payload always includes full persisted finding state via
          ``to_dict(include_state=True)`` so clients can rehydrate discussion
          history (``discussion_turns``) when revisiting completed findings.
        - ``None`` now means strictly "index out of range" (or missing state).
        """
        if not self.state or not self.state.findings:
            return None
        if index < 0 or index >= len(self.state.findings):
            return None

        finding = self.state.findings[index]
        self.current_index = index
        persist_session_index(self.state, self.current_index)
        return {
            "finding": finding.to_dict(include_state=True),
            "index": self.current_index,
            "current": self.current_index + 1,
            "total": len(self.state.findings),
            "is_ambiguity": finding.ambiguity_type == 'ambiguous_possibly_intentional',
        }

    async def goto_finding_with_scene_check(self, index: int) -> dict:
        """Jump to a specific finding, checking for scene changes first.

        API behavior cleanup:
        ``complete=True`` here now indicates an invalid/out-of-range target,
        not a terminal finding status.
        """
        change_report = await self.check_scene_changes()
        index_change = await self.check_index_changes()
        finding = self.goto_finding(index)

        result = {"scene_change": change_report, "index_change": index_change}
        if finding is None:
            result["complete"] = True
            result["message"] = "Finding not available (out of range)."
        else:
            result["complete"] = False
            result.update(finding)

        return result

    def skip_to_lens(self, target_lens: str) -> Optional[dict]:
        """Skip forward to findings from a specific lens group."""
        self.current_index = next_index_for_lens(
            self.state.findings,
            self.current_index,
            target_lens,
        )

        persist_session_index(self.state, self.current_index)
        finding = self.get_current_finding()
        if finding is not None:
            return finding
        return self._jump_to_first_unresolved_finding()

    def accept_finding(self) -> dict:
        """Accept the current finding."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        apply_acceptance(finding, self.state.learning)

        # Auto-save
        persist_finding(self.state, finding)
        persist_session_learning(self.state)

        return {"status": "accepted", "finding_number": finding.number}

    def reject_finding(self, reason: str = "") -> dict:
        """Reject the current finding."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        apply_rejection(finding, self.state.learning, reason)

        # Auto-save
        persist_finding(self.state, finding)
        persist_session_learning(self.state)

        return {"status": "rejected", "finding_number": finding.number}

    def mark_ambiguity(self, intentional: bool) -> dict:
        """Mark current finding's ambiguity as intentional or accidental."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        record_ambiguity_answer(
            finding,
            self.state.learning,
            intentional=intentional,
        )

        # Auto-save
        persist_session_learning(self.state)

        label = "intentional" if intentional else "accidental"
        return {"status": f"marked_{label}", "finding_number": finding.number}

    @staticmethod
    def _apply_discussion_status_to_finding(finding: Finding, status: str) -> None:
        """Apply discussion outcome status to finding using canonical persisted states.

        Discussion may return conversational outcomes (e.g. ``conceded``).
        Persisted finding status should use canonical workflow states.
        """
        apply_discussion_status(finding, status)

    async def discuss(self, message: str) -> dict:
        """Send a discussion message about the current finding."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        change_report = await self.check_scene_changes()
        index_change = await self.check_index_changes()
        scene_changed = change_report is not None

        finding = self.state.findings[self.current_index]
        response_text, status = await handle_discussion(
            self.state, finding, message, scene_changed=scene_changed
        )

        self._apply_discussion_status_to_finding(finding, status)

        # Auto-save
        persist_finding(self.state, finding)
        persist_discussion_history(self.state)
        persist_session_learning(self.state)

        result = {
            "response": response_text,
            "status": status,
            "finding_status": finding.status,
            "scene_change": change_report,
            "index_change": index_change,
        }

        if status in ('revised', 'escalated', 'withdrawn') or scene_changed:
            result["finding"] = finding.to_dict(include_state=True)
        if status in ('revised', 'escalated') and finding.revision_history:
            result["revision_history"] = finding.revision_history

        return result

    async def discuss_stream(self, message: str):
        """Stream a discussion response about the current finding token-by-token."""
        if not self.state or self.current_index >= len(self.state.findings):
            yield ("done", {"error": "No active finding"})
            return

        change_report = await self.check_scene_changes()
        index_change = await self.check_index_changes()
        scene_changed = change_report is not None

        if change_report:
            yield ("scene_change", change_report)

        finding = self.state.findings[self.current_index]

        async for chunk_type, data in handle_discussion_stream(
            self.state, finding, message, scene_changed=scene_changed
        ):
            if chunk_type == "token":
                yield ("token", data)
            elif chunk_type == "done":
                response_text = data["response"]
                status = data["status"]

                self._apply_discussion_status_to_finding(finding, status)

                # Auto-save
                persist_finding(self.state, finding)
                persist_discussion_history(self.state)
                persist_session_learning(self.state)

                result = {
                    "response": response_text,
                    "status": status,
                    "finding_status": finding.status,
                    "scene_change": change_report,
                    "index_change": index_change,
                }

                if status in ('revised', 'escalated', 'withdrawn') or scene_changed:
                    result["finding"] = finding.to_dict(include_state=True)
                if status in ('revised', 'escalated') and finding.revision_history:
                    result["revision_history"] = finding.revision_history

                yield ("done", result)

    def save_learning(self) -> dict:
        """Export LEARNING.md to project directory (DB is already up to date)."""
        if not self.state:
            return {"error": "No active session"}

        filepath = export_learning_markdown(self.state.project_path)
        return {"saved": True, "path": str(filepath)}

    def check_saved_session(self, project_path: str) -> dict:
        """Check if an active session exists for the project."""
        project = Path(project_path)
        if not project.exists():
            return {"exists": False}

        return check_active_session(project)

    def get_session_info(self) -> dict:
        """Get current session state info."""
        if not self.state:
            return {"active": False}

        return {
            "active": True,
            **self._build_summary(),
            "findings_status": [
                {
                    "number": f.number,
                    "severity": f.severity,
                    "lens": f.lens,
                    "status": f.status,
                    "location": f.location,
                    "evidence": f.evidence,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "scene_path": f.scene_path,
                }
                for f in self.state.findings
            ]
        }

    def get_scene_content(self) -> Optional[str]:
        """Get the scene text content."""
        if not self.state:
            return None
        return self.state.scene_content

    def save_current_session(self) -> dict:
        """Save the current session state (already auto-saved, this is a no-op)."""
        if not self.state:
            return {"error": "No active session"}
        return {"saved": True, "message": "Session is auto-saved"}

    def clear_session(self) -> dict:
        """Clear/abandon the current session."""
        if not self.state:
            return {"error": "No active session"}
        
        if self.state.session_id and self.state.db_conn:
            abandon_active_session(self.state.project_path)
        
        # Reset manager state
        self.state = None
        self.results = None
        self.current_index = 0
        self.analysis_progress = None
        
        return {"cleared": True, "message": "Session abandoned"}


class ResumeScenePathError(FileNotFoundError):
    """Raised when the saved scene path for a resumable session is invalid."""

    def __init__(
        self,
        message: str,
        *,
        saved_scene_path: str,
        attempted_scene_path: str,
        project_path: str,
        override_provided: bool,
        saved_scene_paths: Optional[list[str]] = None,
        missing_scene_paths: Optional[list[str]] = None,
    ):
        super().__init__(message)
        self.saved_scene_path = saved_scene_path
        self.attempted_scene_path = attempted_scene_path
        self.project_path = project_path
        self.override_provided = override_provided
        self.saved_scene_paths = saved_scene_paths or ([saved_scene_path] if saved_scene_path else [])
        self.missing_scene_paths = missing_scene_paths or ([attempted_scene_path] if attempted_scene_path else [])
