"""
Server-side session manager for the Web UI.
Bridges the web layer to existing lit-critic modules.
"""

import asyncio
from pathlib import Path
from typing import Optional

from server.config import INDEX_FILES, OPTIONAL_FILES, AVAILABLE_MODELS, DEFAULT_MODEL, resolve_api_key
from server.llm import create_client
from server.models import SessionState, Finding, LearningData, LensResult, CoordinatorError
from server.learning import load_learning, save_learning_to_file
from server.discussion import handle_discussion, handle_discussion_stream
from server.session import (
    session_exists, save_session, load_session, delete_session,
    validate_session, get_session_file_path, detect_and_apply_scene_changes
)
from server.api import run_lens, run_coordinator, run_coordinator_chunked


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
        self.skip_minor: bool = False
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
        """Load all index files from the project directory."""
        indexes = {}
        loaded = []
        missing = []

        for filename in INDEX_FILES:
            filepath = project_path / filename
            if filepath.exists():
                indexes[filename] = filepath.read_text(encoding='utf-8')
                loaded.append(filename)
            else:
                indexes[filename] = ""
                missing.append(filename)

        for filename in OPTIONAL_FILES:
            filepath = project_path / filename
            if filepath.exists():
                indexes[filename] = filepath.read_text(encoding='utf-8')
                loaded.append(filename)

        return indexes, loaded, missing

    def _load_scene(self, scene_path: Path) -> str:
        """Load the scene file."""
        if not scene_path.exists():
            raise FileNotFoundError(f"Scene file not found: {scene_path}")
        return scene_path.read_text(encoding='utf-8')

    async def start_analysis(self, scene_path: str, project_path: str, api_key: str,
                             model: str = DEFAULT_MODEL) -> dict:
        """Start a new analysis. Returns summary info. Populates self.state."""
        project = Path(project_path)
        scene = Path(scene_path)

        if not project.exists():
            raise FileNotFoundError(f"Project directory not found: {project}")

        # Validate model
        if model not in AVAILABLE_MODELS:
            model = DEFAULT_MODEL

        # Load files
        indexes, loaded_files, missing_files = self._load_project_files(project)
        scene_content = self._load_scene(scene)

        # Load learning
        learning = load_learning(project)

        # Initialize provider-agnostic client
        provider = AVAILABLE_MODELS[model]["provider"]
        client = create_client(provider, api_key)

        # Create session state
        self.state = SessionState(
            client=client,
            scene_content=scene_content,
            scene_path=str(scene),
            project_path=project,
            indexes=indexes,
            learning=learning,
            model=model,
        )

        # Set up progress tracking
        self.analysis_progress = AnalysisProgress()

        # Run analysis with progress tracking
        self.analysis_progress.add_event("status", {"message": "Running 5 lenses in parallel..."})

        model_id = self.state.model_id
        max_tokens = self.state.model_max_tokens

        lens_names = ["prose", "structure", "logic", "clarity", "continuity"]
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

        # Coordinate (chunked: prose → structure → coherence)
        self.analysis_progress.add_event("status", {"message": "Coordinating results (chunked)..."})

        def _coord_progress(event_type: str, data: dict):
            self.analysis_progress.add_event(event_type, data)

        try:
            coordinated = await run_coordinator_chunked(
                client, lens_results, scene_content,
                model=model_id, max_tokens=max_tokens,
                progress_callback=_coord_progress,
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
        self.state.glossary_issues = coordinated.get("glossary_issues", [])
        self.current_index = 0
        self.skip_minor = False

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

    async def resume_session(self, project_path: str, api_key: str) -> dict:
        """Resume a saved session. Returns summary info."""
        project = Path(project_path)

        session_data = load_session(project)
        if not session_data:
            raise FileNotFoundError("No saved session found in project directory.")

        scene_path_str = session_data.get("scene_path", "")
        if not scene_path_str:
            raise ValueError("Session file is corrupted (missing scene path)")

        scene_path = Path(scene_path_str)

        # Load files
        indexes, loaded_files, missing_files = self._load_project_files(project)
        scene_content = self._load_scene(scene_path)

        # Validate
        is_valid, error_msg = validate_session(session_data, scene_content, str(scene_path))
        if not is_valid:
            raise ValueError(f"Cannot resume session: {error_msg}")

        # Load learning
        learning = load_learning(project)
        learning_session = session_data.get("learning_session", {})
        learning.session_rejections = learning_session.get("session_rejections", [])
        learning.session_acceptances = learning_session.get("session_acceptances", [])
        learning.session_ambiguity_answers = learning_session.get("session_ambiguity_answers", [])

        # Restore model from session
        saved_model = session_data.get("model", DEFAULT_MODEL)
        if saved_model not in AVAILABLE_MODELS:
            saved_model = DEFAULT_MODEL

        # Initialize provider-agnostic client
        provider = AVAILABLE_MODELS[saved_model]["provider"]
        client = create_client(provider, api_key)

        # Create session state
        self.state = SessionState(
            client=client,
            scene_content=scene_content,
            scene_path=str(scene_path),
            project_path=project,
            indexes=indexes,
            learning=learning,
            findings=[Finding.from_dict(f) for f in session_data.get("findings", [])],
            glossary_issues=session_data.get("glossary_issues", []),
            discussion_history=session_data.get("discussion_history", []),
            model=saved_model,
        )

        self.current_index = session_data.get("current_index", 0)
        self.skip_minor = session_data.get("skip_minor", False)

        return self._build_summary()

    def _build_summary(self) -> dict:
        """Build the summary response dict."""
        if not self.state:
            return {}

        summary = {
            "scene_path": self.state.scene_path,
            "scene_name": Path(self.state.scene_path).name,
            "project_path": str(self.state.project_path),
            "total_findings": len(self.state.findings),
            "current_index": self.current_index,
            "skip_minor": self.skip_minor,
            "glossary_issues": self.state.glossary_issues,
            "counts": {"critical": 0, "major": 0, "minor": 0},
            "lens_counts": {},
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

        # Learning info
        summary["learning"] = {
            "review_count": self.state.learning.review_count,
            "preferences": len(self.state.learning.preferences),
            "blind_spots": len(self.state.learning.blind_spots),
        }

        return summary

    async def check_scene_changes(self) -> Optional[dict]:
        """Check for scene file changes and apply line adjustments + re-evaluation.

        Returns None if no change, or a change report dict.
        Should be called before any finding transition in the web UI.
        """
        if not self.state:
            return None
        return await detect_and_apply_scene_changes(self.state, self.current_index)

    def get_current_finding(self) -> Optional[dict]:
        """Get the current finding, respecting skip settings. Returns None if all done."""
        if not self.state or not self.state.findings:
            return None

        while self.current_index < len(self.state.findings):
            finding = self.state.findings[self.current_index]

            # Skip withdrawn findings (may have been withdrawn by re-evaluation)
            if finding.status == 'withdrawn':
                self.current_index += 1
                continue

            # Skip minor if enabled
            if self.skip_minor and finding.severity.lower() == 'minor':
                self.current_index += 1
                continue

            return {
                "finding": finding.to_dict(include_state=True),
                "index": self.current_index,
                "current": self.current_index + 1,
                "total": len(self.state.findings),
                "is_ambiguity": finding.ambiguity_type == 'ambiguous_possibly_intentional',
            }

        return None  # All findings processed

    async def advance_with_scene_check(self) -> dict:
        """Move to next finding, checking for scene changes first.

        Returns a dict with:
            scene_change: change report (or None)
            finding: next finding dict (or complete message)
        """
        self.current_index += 1
        change_report = await self.check_scene_changes()
        finding = self.get_current_finding()

        result = {"scene_change": change_report}
        if finding is None:
            result["complete"] = True
            result["message"] = "All findings have been presented."
        else:
            result["complete"] = False
            result.update(finding)

        return result

    def advance(self) -> Optional[dict]:
        """Move to next finding and return it (sync, no scene check)."""
        self.current_index += 1
        return self.get_current_finding()

    def skip_minor_findings(self) -> Optional[dict]:
        """Enable skip minor and advance."""
        self.skip_minor = True
        self.current_index += 1
        return self.get_current_finding()

    def goto_finding(self, index: int) -> Optional[dict]:
        """Jump to a specific finding by index.

        Returns the full finding dict, or None if index is out of range.
        Skips withdrawn findings (returns None in that case too).
        """
        if not self.state or not self.state.findings:
            return None
        if index < 0 or index >= len(self.state.findings):
            return None

        finding = self.state.findings[index]
        if finding.status == 'withdrawn':
            return None

        self.current_index = index
        return {
            "finding": finding.to_dict(include_state=True),
            "index": self.current_index,
            "current": self.current_index + 1,
            "total": len(self.state.findings),
            "is_ambiguity": finding.ambiguity_type == 'ambiguous_possibly_intentional',
        }

    async def goto_finding_with_scene_check(self, index: int) -> dict:
        """Jump to a specific finding, checking for scene changes first.

        Returns a dict with:
            scene_change: change report (or None)
            finding: finding dict (or error)
        """
        change_report = await self.check_scene_changes()
        finding = self.goto_finding(index)

        result = {"scene_change": change_report}
        if finding is None:
            result["complete"] = True
            result["message"] = "Finding not available (withdrawn or out of range)."
        else:
            result["complete"] = False
            result.update(finding)

        return result

    def skip_to_lens(self, target_lens: str) -> Optional[dict]:
        """Skip forward to findings from a specific lens group."""
        self.current_index += 1
        while self.current_index < len(self.state.findings):
            finding = self.state.findings[self.current_index]
            lens = finding.lens.lower()

            if target_lens == 'structure' and lens == 'prose':
                self.current_index += 1
                continue
            elif target_lens == 'coherence' and lens in ['prose', 'structure']:
                self.current_index += 1
                continue
            break

        return self.get_current_finding()

    def accept_finding(self) -> dict:
        """Accept the current finding."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        finding.status = 'accepted'
        self.state.learning.session_acceptances.append({
            "lens": finding.lens,
            "pattern": finding.evidence[:100]
        })

        return {"status": "accepted", "finding_number": finding.number}

    def reject_finding(self, reason: str = "") -> dict:
        """Reject the current finding."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        finding.status = 'rejected'
        finding.author_response = reason
        self.state.learning.session_rejections.append({
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
            "reason": reason
        })

        return {"status": "rejected", "finding_number": finding.number}

    def mark_ambiguity(self, intentional: bool) -> dict:
        """Mark current finding's ambiguity as intentional or accidental."""
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        finding = self.state.findings[self.current_index]
        self.state.learning.session_ambiguity_answers.append({
            "location": finding.location,
            "description": finding.evidence[:100],
            "intentional": intentional
        })

        label = "intentional" if intentional else "accidental"
        return {"status": f"marked_{label}", "finding_number": finding.number}

    async def discuss(self, message: str) -> dict:
        """Send a discussion message about the current finding.
        
        Returns dict with:
            - response: critic's display text
            - status: discussion status (continue, accepted, rejected, conceded, revised, withdrawn, escalated)
            - finding_status: current finding status
            - finding: updated finding dict (included when finding was revised/escalated/withdrawn)
            - revision_history: previous versions (included when finding was revised/escalated)
            - scene_change: change report dict (included when scene file was edited since last check)
        """
        if not self.state or self.current_index >= len(self.state.findings):
            return {"error": "No active finding"}

        # Check for scene changes before building the discussion prompt.
        # This updates state.scene_content so the critic sees the latest text.
        change_report = await self.check_scene_changes()
        scene_changed = change_report is not None

        finding = self.state.findings[self.current_index]
        response_text, status = await handle_discussion(
            self.state, finding, message, scene_changed=scene_changed
        )

        if status == 'accepted':
            finding.status = 'accepted'
        elif status in ('rejected', 'conceded'):
            finding.status = 'rejected'
        elif status == 'revised':
            finding.status = 'revised'
        elif status == 'withdrawn':
            finding.status = 'withdrawn'
        elif status == 'escalated':
            finding.status = 'escalated'

        result = {
            "response": response_text,
            "status": status,
            "finding_status": finding.status,
            "scene_change": change_report,
        }

        # Include updated finding data when it changed (by discussion or by scene re-evaluation)
        if status in ('revised', 'escalated', 'withdrawn') or scene_changed:
            result["finding"] = finding.to_dict(include_state=True)
        if status in ('revised', 'escalated') and finding.revision_history:
            result["revision_history"] = finding.revision_history

        return result

    async def discuss_stream(self, message: str):
        """Stream a discussion response about the current finding token-by-token.
        
        Async generator that yields (chunk_type, data) tuples:
            ("scene_change", change_report) — emitted before streaming if scene was edited
            ("token", text_chunk)           — a streaming text token
            ("done", result_dict)           — final result with same shape as discuss() return
        """
        if not self.state or self.current_index >= len(self.state.findings):
            yield ("done", {"error": "No active finding"})
            return

        # Check for scene changes before building the discussion prompt.
        change_report = await self.check_scene_changes()
        scene_changed = change_report is not None

        # Emit scene change event before streaming tokens so the UI can notify early
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

                # Apply finding status (same as discuss())
                if status == 'accepted':
                    finding.status = 'accepted'
                elif status in ('rejected', 'conceded'):
                    finding.status = 'rejected'
                elif status == 'revised':
                    finding.status = 'revised'
                elif status == 'withdrawn':
                    finding.status = 'withdrawn'
                elif status == 'escalated':
                    finding.status = 'escalated'

                result = {
                    "response": response_text,
                    "status": status,
                    "finding_status": finding.status,
                    "scene_change": change_report,
                }

                # Include updated finding data when it changed
                if status in ('revised', 'escalated', 'withdrawn') or scene_changed:
                    result["finding"] = finding.to_dict(include_state=True)
                if status in ('revised', 'escalated') and finding.revision_history:
                    result["revision_history"] = finding.revision_history

                yield ("done", result)

    def save_current_session(self) -> dict:
        """Save session to disk."""
        if not self.state:
            return {"error": "No active session"}

        filepath = save_session(self.state, self.current_index, self.skip_minor)
        return {"saved": True, "path": str(filepath)}

    def save_learning(self) -> dict:
        """Save LEARNING.md to project directory."""
        if not self.state:
            return {"error": "No active session"}

        filepath = save_learning_to_file(self.state.learning, self.state.project_path)
        return {"saved": True, "path": str(filepath)}

    def clear_session(self) -> dict:
        """Delete saved session file."""
        if not self.state:
            return {"error": "No active session"}

        deleted = delete_session(self.state.project_path)
        return {"deleted": deleted}

    def check_saved_session(self, project_path: str) -> dict:
        """Check if a saved session exists for the project."""
        project = Path(project_path)
        if not project.exists():
            return {"exists": False}

        if session_exists(project):
            session_data = load_session(project)
            if session_data:
                return {
                    "exists": True,
                    "scene_path": session_data.get("scene_path", ""),
                    "saved_at": session_data.get("saved_at", ""),
                    "current_index": session_data.get("current_index", 0),
                    "total_findings": len(session_data.get("findings", [])),
                }

        return {"exists": False}

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
                }
                for f in self.state.findings
            ]
        }

    def get_scene_content(self) -> Optional[str]:
        """Get the scene text content."""
        if not self.state:
            return None
        return self.state.scene_content
