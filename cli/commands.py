"""
CLI subcommand implementations for the lit-critic system.

Subcommands::

    lit-critic sessions start  --scene X --project Y [--mode preflight|quick|deep] [--api-key K]
    lit-critic sessions resume --project Y [--api-key K]
    lit-critic config show
    lit-critic config set frontier=sonnet deep=sonnet quick=haiku
    lit-critic sessions list   --project Y
    lit-critic sessions show   ID --project Y
    lit-critic sessions delete ID --project Y
    lit-critic scenes list     --project Y
    lit-critic learning list   --project Y
    lit-critic learning add    --project Y
    lit-critic learning update ID --project Y
    lit-critic learning export --project Y
    lit-critic learning reset  --project Y
"""

import argparse
import os
import sys
from pathlib import Path

from lit_platform.repo_preflight import MARKER_FILENAME, validate_repo_path
from lit_platform.user_config import get_model_slots, get_repo_path, set_model_slots, set_repo_path
from lit_platform.runtime.model_slots import (
    default_model_slots,
    resolve_models_for_mode,
    validate_model_slots,
)
from lit_platform.session_state_machine import restore_learning_session
from lit_platform.models import SessionState, Finding, CoordinatorError
from lit_platform.services.code_checks import run_code_checks
from lit_platform.services.analysis_service import (
    DEFAULT_MODEL,
    create_client,
    get_available_models,
    is_known_model,
    resolve_api_key,
    resolve_model,
    run_analysis,
)
from lit_platform.services import (
    check_active_session,
    load_active_session,
    validate_session,
    complete_active_session,
    abandon_active_session,
    delete_session_by_id,
    list_sessions,
    get_session_detail,
    load_learning,
    load_learning_from_db,
    generate_learning_markdown,
    export_learning_markdown,
    reset_learning,
)
from lit_platform.persistence import (
    CATEGORY_AMBIGUITY_ACCIDENTAL,
    CATEGORY_AMBIGUITY_INTENTIONAL,
    CATEGORY_BLIND_SPOT,
    CATEGORY_PREFERENCE,
    CATEGORY_RESOLUTION,
    ExtractionStore,
    LearningStore,
    SessionStore,
    get_connection,
)
from lit_platform.services.project_knowledge_service import ensure_project_knowledge_fresh
from lit_platform.services.project_knowledge_service import refresh_project_knowledge
from lit_platform.services.knowledge_review_service import (
    delete_entity as delete_knowledge_entity,
    delete_override as delete_knowledge_override,
    export_knowledge_markdown,
    get_knowledge_review,
    submit_override,
)
from lit_platform.services.scene_projection_service import (
    list_scene_projections,
)
from lit_platform.services.rename_service import rename_scene

from .interface import load_project_files, load_scene, print_summary
from .session_loop import run_interactive_session


MAX_REPO_PATH_RETRIES = 3


def _resolve_repo_path_candidate() -> tuple[str | None, str]:
    env_value = os.environ.get("LIT_CRITIC_REPO_PATH", "").strip()
    if env_value:
        return env_value, "environment variable LIT_CRITIC_REPO_PATH"

    config_value = (get_repo_path() or "").strip()
    if config_value:
        return config_value, "user config"

    return None, "user config"


def _ensure_repo_path_preflight() -> str:
    repo_path, source = _resolve_repo_path_candidate()
    validation = validate_repo_path(repo_path)
    if validation.ok:
        return validation.path or str(Path(repo_path).resolve())

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive:
        raise RuntimeError(
            "Repository preflight failed: "
            f"{validation.message}\n"
            "Set a valid repo path in user config or export LIT_CRITIC_REPO_PATH. "
            f"The path must be a directory containing {MARKER_FILENAME}."
        )

    print("\nRepository path preflight failed.")
    print(f"  Current source: {source}")

    attempts = 0
    current_validation = validation
    while attempts < MAX_REPO_PATH_RETRIES:
        attempts += 1
        print(f"  Reason: {current_validation.message}")
        try:
            corrected = input(
                f"  Enter lit-critic repo path (contains {MARKER_FILENAME}) "
                "or 'q' to abort: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Repository path setup aborted.")

        if corrected.lower() in {"q", "quit", "exit"}:
            raise RuntimeError("Repository path setup aborted.")

        current_validation = validate_repo_path(corrected)
        if current_validation.ok:
            assert current_validation.path is not None
            set_repo_path(current_validation.path)
            print(f"  ✓ Saved repo path to user config: {current_validation.path}")
            return current_validation.path

    raise RuntimeError(
        "Repository preflight failed after multiple attempts. "
        f"Please set a valid path containing {MARKER_FILENAME}."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Subcommand: analyze
# ---------------------------------------------------------------------------

async def cmd_analyze(args):
    """Run a new multi-lens analysis."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    scene_path = Path(args.scene)

    # Check for active session
    active = check_active_session(project_path)
    if active.get("exists"):
        n = active["total_findings"]
        idx = active["current_index"]
        scene = Path(active["scene_path"]).name
        print(f"\nWarning: Active session found ({scene}, {idx}/{n} findings reviewed).")
        print("Starting a new analysis will close this session.\n")
        try:
            choice = input("  (c)omplete / (d)iscard / (a)bort? ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if choice.startswith('c'):
            if complete_active_session(project_path):
                print("  ✓ Previous session marked completed.")
            else:
                print("  ! Previous session has unresolved findings and cannot be marked completed.")
                print("    Choose discard or resume it to finish all findings.")
                sys.exit(1)
        elif choice.startswith('d'):
            abandon_active_session(project_path)
            print("  ✓ Previous session discarded.")
        else:
            print("Aborted.")
            sys.exit(0)

    # Resolve models from depth mode + configured model slots.
    mode = getattr(args, 'mode', 'deep')
    try:
        resolved_models = resolve_models_for_mode(mode, get_model_slots())
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    analysis_model = resolved_models["analysis_model"]
    discussion_model = resolved_models["discussion_model"]

    model_cfg = resolve_model(analysis_model)
    provider = model_cfg["provider"]
    try:
        api_key = resolve_api_key(provider, args.api_key)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        client = create_client(provider, api_key)
    except (ValueError, ImportError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Resolve discussion model if provided
    discussion_client = None
    discussion_model_cfg = None
    if discussion_model:
        discussion_model_cfg = resolve_model(discussion_model)
        discussion_provider = discussion_model_cfg["provider"]
        
        # Only create a new client if the provider differs
        if discussion_provider != provider:
            try:
                discussion_api_key = resolve_api_key(discussion_provider, args.api_key)
                discussion_client = create_client(discussion_provider, discussion_api_key)
            except (ValueError, ImportError) as e:
                print(f"Error creating discussion client: {e}")
                sys.exit(1)
        else:
            # Same provider — reuse the same client
            discussion_client = client

    # Load files
    print("\nLoading project files...")
    indexes = load_project_files(project_path)

    print("\nLoading scene...")
    try:
        scene = load_scene(scene_path)
        print(f"  ✓ Loaded {scene_path.name} ({len(scene)} characters)")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Load learning and inject directly into indexes so that analysis prompts
    # always reflect the current DB state (no need for a LEARNING.md file on disk).
    print("\nLoading learning data...")
    learning = load_learning(project_path)
    indexes['LEARNING.md'] = generate_learning_markdown(learning)
    print(f"  ✓ Review count: {learning.review_count}")
    print(f"  ✓ Preferences: {len(learning.preferences)}")
    print(f"  ✓ Blind spots: {len(learning.blind_spots)}")
    print(f"  ✓ Analysis mode: {mode}")
    print(f"  ✓ Analysis model: {analysis_model} ({model_cfg['id']})")
    if discussion_model:
        print(f"  ✓ Discussion model: {discussion_model} ({discussion_model_cfg['id']})")

    # Run code checks (deterministic, free, instant) before sending to LLM.
    print("\nRunning code checks...")
    code_findings = run_code_checks(scene, indexes)
    if code_findings:
        by_sev: dict[str, int] = {"critical": 0, "major": 0, "minor": 0}
        for f in code_findings:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        parts = [f"{v} {k}" for k, v in by_sev.items() if v > 0]
        print(f"  ✓ Code checks: {len(code_findings)} finding(s) ({', '.join(parts)})")
    else:
        print("  ✓ Code checks: all clear")

    # Create session state
    state = SessionState(
        client=client,
        scene_content=scene,
        scene_path=str(scene_path),
        project_path=project_path,
        indexes=indexes,
        learning=learning,
        model=analysis_model,
        discussion_model=discussion_model,
        discussion_client=discussion_client,
    )

    # Run analysis
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    try:
        results = await run_analysis(
            client, scene, indexes,
            model=state.model_id, max_tokens=state.model_max_tokens,
        )
    except CoordinatorError as e:
        print(f"\nError during coordination: {e}")
        if e.raw_output:
            print(f"Raw output: {e.raw_output[:500]}...")
        if e.attempts > 1:
            print(f"(failed after {e.attempts} attempts)")
        sys.exit(1)

    # Merge code findings (origin='code') into LLM results.
    # LLM finding numbers are offset so the combined list is contiguous: 1..K (code) K+1..N (LLM).
    code_count = len(code_findings)
    if code_count > 0:
        for f_dict in results.get("findings", []):
            f_dict["number"] = code_count + f_dict.get("number", 0)
        code_dicts = []
        for f in code_findings:
            d = f.to_dict(include_state=True)
            d["scene_path"] = str(scene_path)
            code_dicts.append(d)
        results["findings"] = code_dicts + results.get("findings", [])

    print_summary(results)
    await run_interactive_session(state, results)


# ---------------------------------------------------------------------------
# Subcommand: resume
# ---------------------------------------------------------------------------

async def cmd_resume(args):
    """Resume an active session."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    print("\nChecking for active session...")
    session_data = load_active_session(project_path)

    if not session_data:
        print("Error: No active session found.")
        print("  Start a new review with: lit-critic analyze --scene X --project Y")
        sys.exit(1)

    # Extract the DB connection (caller takes ownership)
    conn = session_data.pop("_conn")

    scene_path_str = session_data.get("scene_path", "")
    if not scene_path_str:
        print("Error: Session data is corrupted (missing scene path)")
        conn.close()
        sys.exit(1)

    scene_path = Path(scene_path_str)
    print(f"  ✓ Found active session for: {scene_path.name}")
    print(f"  ✓ Created: {session_data.get('created_at', 'unknown')}")

    # Load scene
    print("\nLoading scene...")
    try:
        scene = load_scene(scene_path)
        print(f"  ✓ Loaded {scene_path.name} ({len(scene)} characters)")
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        print("  Saved scene path is missing (likely from another machine/path).")

        try:
            corrected = input(
                "  Enter corrected scene file path (leave blank to abort): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            conn.close()
            sys.exit(0)

        if not corrected:
            print("Aborted.")
            conn.close()
            sys.exit(1)

        corrected_path = Path(corrected)
        if not corrected_path.exists():
            print(f"Error: Scene file not found: {corrected_path}")
            conn.close()
            sys.exit(1)

        scene_path = corrected_path
        session_data["scene_path"] = str(scene_path)
        SessionStore.update_scene_path(conn, session_data["session_id"], str(scene_path))

        scene = load_scene(scene_path)
        print(f"  ✓ Loaded {scene_path.name} ({len(scene)} characters)")

    # Validate scene hash
    is_valid, error_msg = validate_session(session_data, scene, str(scene_path))
    if not is_valid:
        print(f"Warning: {error_msg}")
        print("  The scene has been modified — findings may be stale.")
        print("  Scene changes will be detected on the first finding transition.")

    # Load project files
    print("\nLoading project files...")
    indexes = load_project_files(project_path)

    # Load learning from DB
    learning = load_learning_from_db(conn)

    # Restore session learning state
    restore_learning_session(learning, session_data.get("learning_session", {}))

    print(f"  ✓ Review count: {learning.review_count}")
    print(f"  ✓ Preferences: {len(learning.preferences)}")

    # Resolve model
    saved_model = session_data.get("model", DEFAULT_MODEL)
    if not is_known_model(saved_model):
        print(f"  Warning: Model '{saved_model}' unavailable, using {DEFAULT_MODEL}")
        saved_model = DEFAULT_MODEL

    model_cfg = resolve_model(saved_model)
    provider = model_cfg["provider"]
    print(f"  ✓ Analysis model: {saved_model} ({model_cfg['id']})")

    # Restore discussion model if present in session
    saved_discussion_model = session_data.get("discussion_model")
    if saved_discussion_model and not is_known_model(saved_discussion_model):
        print(f"  Warning: Discussion model '{saved_discussion_model}' unavailable, using same as analysis")
        saved_discussion_model = None

    try:
        api_key = resolve_api_key(provider, args.api_key)
    except ValueError as e:
        print(f"Error: {e}")
        conn.close()
        sys.exit(1)

    try:
        client = create_client(provider, api_key)
    except (ValueError, ImportError) as e:
        print(f"Error: {e}")
        conn.close()
        sys.exit(1)

    # Create discussion client if using different model
    discussion_client = None
    if saved_discussion_model:
        discussion_model_cfg = resolve_model(saved_discussion_model)
        discussion_provider = discussion_model_cfg["provider"]
        print(f"  ✓ Discussion model: {saved_discussion_model} ({discussion_model_cfg['id']})")
        
        # Only create a new client if the provider differs
        if discussion_provider != provider:
            try:
                discussion_api_key = resolve_api_key(discussion_provider, args.api_key)
                discussion_client = create_client(discussion_provider, discussion_api_key)
            except (ValueError, ImportError) as e:
                print(f"Error creating discussion client: {e}")
                conn.close()
                sys.exit(1)
        else:
            # Same provider — reuse the same client
            discussion_client = client

    # Rebuild session state
    state = SessionState(
        client=client,
        scene_content=scene,
        scene_path=str(scene_path),
        project_path=project_path,
        indexes=indexes,
        learning=learning,
        findings=[Finding.from_dict(f) for f in session_data.get("findings", [])],
        glossary_issues=session_data.get("glossary_issues", []),
        discussion_history=session_data.get("discussion_history", []),
        model=saved_model,
        discussion_model=saved_discussion_model,
        discussion_client=discussion_client,
        db_conn=conn,
        session_id=session_data["session_id"],
    )

    start_index = session_data.get("current_index", 0)
    total = len(state.findings)

    print(f"\n  ✓ Resuming from finding #{start_index + 1} of {total}")

    print("\n" + "=" * 60)
    print("RESUMING SESSION")
    print("=" * 60)
    await run_interactive_session(
        state, results=None,
        start_index=start_index,
    )


# ---------------------------------------------------------------------------
# Subcommand: config
# ---------------------------------------------------------------------------

def cmd_config(args):
    """Manage persistent model-slot configuration."""
    action = args.config_action

    if action == "show":
        slots = default_model_slots()
        slots.update(get_model_slots() or {})
        print("Model slots:")
        print(f"  frontier = {slots['frontier']}")
        print(f"  deep     = {slots['deep']}")
        print(f"  quick    = {slots['quick']}")
        return

    if action == "set":
        current = default_model_slots()
        current.update(get_model_slots() or {})

        updates: dict[str, str] = {}
        for assignment in args.assignments:
            if "=" not in assignment:
                print(f"Error: Invalid assignment '{assignment}'. Expected slot=model.")
                sys.exit(1)
            slot, model = assignment.split("=", 1)
            slot = slot.strip().lower()
            model = model.strip()
            if slot not in {"frontier", "deep", "quick"}:
                print(f"Error: Unknown slot '{slot}'. Use frontier, deep, or quick.")
                sys.exit(1)
            if not model:
                print(f"Error: Missing model for slot '{slot}'.")
                sys.exit(1)
            updates[slot] = model

        current.update(updates)
        try:
            validated = validate_model_slots(current)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

        set_model_slots(validated)
        print("✓ Updated model slots:")
        print(f"  frontier = {validated['frontier']}")
        print(f"  deep     = {validated['deep']}")
        print(f"  quick    = {validated['quick']}")


# ---------------------------------------------------------------------------
# Subcommand: sessions
# ---------------------------------------------------------------------------

async def cmd_sessions(args):
    """Manage saved sessions."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    action = args.sessions_action

    if action == 'start':
        refresh_result = ensure_project_knowledge_fresh(project_path)
        if refresh_result.get("refreshed"):
            print(
                "Refreshed project knowledge projections "
                f"(scenes updated: {refresh_result.get('scene_updated', 0)}, "
                f"indexes updated: {refresh_result.get('index_updated', 0)})."
            )
        await cmd_analyze(args)

    elif action == 'resume':
        await cmd_resume(args)

    elif action == 'list':
        sessions = list_sessions(project_path)
        if not sessions:
            print("No sessions found.")
            return
        print(f"\n{'ID':>4}  {'Status':<11}  {'Scene':<25}  {'Findings':>8}  {'Created'}")
        print("-" * 75)
        for s in sessions:
            scene = Path(s.get("scene_path", "?")).name
            total = s.get("total_findings", 0)
            created = s.get("created_at", "?")[:16]
            status = s.get("status", "?")
            print(f"{s['id']:>4}  {status:<11}  {scene:<25}  {total:>8}  {created}")

    elif action == 'show':
        detail = get_session_detail(project_path, args.id)
        if not detail:
            print(f"Session #{args.id} not found.")
            sys.exit(1)
        _print_session_detail(detail)

    elif action == 'delete':
        if delete_session_by_id(project_path, args.id):
            print(f"Session #{args.id} deleted.")
        else:
            print(f"Session #{args.id} not found.")


def _print_session_detail(detail: dict):
    """Pretty-print a session detail."""
    print(f"\nSession #{detail['id']}")
    print(f"  Status:   {detail.get('status', '?')}")
    print(f"  Scene:    {detail.get('scene_path', '?')}")
    print(f"  Model:    {detail.get('model', '?')}")
    print(f"  Created:  {detail.get('created_at', '?')}")
    if detail.get('completed_at'):
        print(f"  Finished: {detail['completed_at']}")

    findings = detail.get("findings", [])
    print(f"  Findings: {len(findings)}")
    if findings:
        counts = {"accepted": 0, "rejected": 0, "withdrawn": 0, "pending": 0}
        for f in findings:
            status = f.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        parts = [f"{v} {k}" for k, v in counts.items() if v > 0]
        print(f"  Breakdown: {', '.join(parts)}")

        print("\n  Finding details:")
        for f in findings:
            number = f.get("number", "?")
            severity = f.get("severity", "?")
            lens = f.get("lens", "?")
            status = f.get("status", "pending")
            turns = f.get("discussion_turns") or []

            print(
                f"    #{number} [{severity}/{lens}] {status}"
                f" — {len(turns)} discussion turn(s)"
            )

            if turns:
                last = turns[-1] if isinstance(turns[-1], dict) else {}
                role_raw = str(last.get("role", "system")).lower()
                role = (
                    "You" if role_raw == "user"
                    else "Critic" if role_raw == "assistant"
                    else "System"
                )
                content = str(last.get("content", "")).replace("\n", " ").strip()
                if len(content) > 100:
                    content = content[:97].rstrip() + "..."
                print(f"      Last: {role}: {content}")


# ---------------------------------------------------------------------------
# Subcommand: learning
# ---------------------------------------------------------------------------

def cmd_learning(args):
    """Manage learning data."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    action = args.learning_action

    if action == 'list':
        learning = load_learning(project_path)
        print(f"\nProject: {learning.project_name}")
        print(f"Review count: {learning.review_count}")
        print(f"\nPreferences ({len(learning.preferences)}):")
        for p in learning.preferences:
            print(f"  • {p.get('description', p)}")
        print(f"\nBlind spots ({len(learning.blind_spots)}):")
        for b in learning.blind_spots:
            print(f"  • {b.get('description', b)}")
        print(f"\nResolutions ({len(learning.resolutions)}):")
        for r in learning.resolutions:
            print(f"  • {r.get('description', r)}")
        print(f"\nAmbiguity — Intentional ({len(learning.ambiguity_intentional)}):")
        for a in learning.ambiguity_intentional:
            print(f"  • {a.get('description', a)}")
        print(f"\nAmbiguity — Accidental ({len(learning.ambiguity_accidental)}):")
        for a in learning.ambiguity_accidental:
            print(f"  • {a.get('description', a)}")

    elif action == 'add':
        category_aliases = {
            "preference": CATEGORY_PREFERENCE,
            "blind-spot": CATEGORY_BLIND_SPOT,
            "resolution": CATEGORY_RESOLUTION,
            "ambiguity-intentional": CATEGORY_AMBIGUITY_INTENTIONAL,
            "ambiguity-accidental": CATEGORY_AMBIGUITY_ACCIDENTAL,
        }

        print("\nCategory options:")
        print("  - preference")
        print("  - blind-spot")
        print("  - resolution")
        print("  - ambiguity-intentional")
        print("  - ambiguity-accidental")

        try:
            raw_category = input("Category: ").strip().lower()
            description = input("Description: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("Cancelled.")
            return

        category = category_aliases.get(raw_category)
        if category is None:
            print(f"Error: Unknown category '{raw_category}'.")
            sys.exit(1)
        if not description:
            print("Error: Description cannot be empty.")
            sys.exit(1)

        conn = get_connection(project_path)
        try:
            entry_id = LearningStore.add_entry(conn, category, description)
        finally:
            conn.close()

        print(f"✓ Added learning entry #{entry_id} ({raw_category}).")

    elif action == 'update':
        print("Learning update: not yet implemented")

    elif action == 'export':
        filepath = export_learning_markdown(project_path)
        print(f"✓ Exported to {filepath}")

    elif action == 'reset':
        try:
            confirm = input("Reset all learning data? This cannot be undone. (y/N): ")
        except (EOFError, KeyboardInterrupt):
            return
        if confirm.strip().lower() in ('y', 'yes'):
            reset_learning(project_path)
            print("✓ Learning data reset.")
        else:
            print("Cancelled.")


def _format_chain_warning(warning: dict) -> str:
    """Format one non-fatal chain warning for CLI output."""
    warning_type = str(warning.get("type") or "unknown")
    scene = str(warning.get("scene") or "?")
    field = str(warning.get("field") or "?")

    if warning_type == "gap":
        target = str(warning.get("target") or "?")
        return f"[{warning_type}] {scene}: {field} references missing scene '{target}'"
    if warning_type == "orphan":
        return f"[{warning_type}] {scene}: no incoming prev/next links"
    if warning_type == "fork":
        target = str(warning.get("target") or "?")
        sources = warning.get("sources") or []
        if isinstance(sources, list) and sources:
            source_text = ", ".join(str(item) for item in sources)
        else:
            source_text = "multiple scenes"
        return f"[{warning_type}] {target}: claimed as next by {source_text}"
    if warning_type == "cycle":
        cycle_path = warning.get("path") or []
        if isinstance(cycle_path, list) and cycle_path:
            cycle_text = " -> ".join(str(item) for item in cycle_path)
        else:
            cycle_text = scene
        return f"[{warning_type}] cycle detected: {cycle_text}"

    return f"[{warning_type}] {scene} ({field})"


def _print_extraction_summary(extraction: dict) -> None:
    """Print extraction summary from knowledge refresh payload."""
    if not extraction:
        print("\nExtraction: no details available")
        return

    attempted = bool(extraction.get("attempted"))
    model_name = extraction.get("model_name") or extraction.get("model_slot")
    scenes_scanned = int(extraction.get("scenes_scanned") or 0)
    extracted = extraction.get("extracted") or []
    skipped_locked = extraction.get("skipped_locked") or []
    failed = extraction.get("failed") or []

    print("\nExtraction:")
    if attempted:
        if model_name:
            print(f"  Attempted: yes ({model_name})")
        else:
            print("  Attempted: yes")
    else:
        print("  Attempted: no")
        reason = extraction.get("reason")
        if reason:
            print(f"  Reason: {reason}")
    print(f"  Scenes scanned: {scenes_scanned}")
    print(f"  Extracted: {len(extracted)}")
    if skipped_locked:
        print(f"  Skipped (locked): {len(skipped_locked)}")
    if failed:
        print(f"  Failed: {len(failed)}")
    error = extraction.get("error")
    if error:
        print(f"  Error: {error}")


def _prompt_knowledge_category() -> str:
    """Prompt for a knowledge review category."""
    print("\nKnowledge categories:")
    print("  - characters")
    print("  - terms")
    print("  - threads")
    print("  - timeline")
    print("  - scene_metadata")

    try:
        return input("Category: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def cmd_knowledge(args):
    """Manage unified knowledge refresh/review/export workflows."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    action = args.knowledge_action

    if action == "refresh":
        result = refresh_project_knowledge(project_path)
        print("Knowledge refresh complete.")
        print(
            f"  Scenes: {result.get('scene_updated', 0)}/{result.get('scene_total', 0)} updated"
        )
        print(
            f"  Indexes: {result.get('index_updated', 0)}/{result.get('index_total', 0)} updated"
        )

        chain_warnings = result.get("chain_warnings") or []
        if chain_warnings:
            print("\nChain warnings:")
            for warning in chain_warnings:
                print(f"  - {_format_chain_warning(warning)}")
        else:
            print("\nChain warnings: none")

        _print_extraction_summary(result.get("extraction") or {})

    elif action == "review":
        category = (getattr(args, "category", None) or "").strip() or _prompt_knowledge_category()
        if not category:
            print("Cancelled.")
            return

        conn = get_connection(project_path)
        try:
            try:
                review = get_knowledge_review(conn, category)
            except ValueError as exc:
                print(f"Error: {exc}")
                sys.exit(1)

            normalized = str(review.get("category") or category)
            key_field = str(review.get("entity_key_field") or "entity_key")
            items = review.get("items") or []
            overrides = review.get("overrides") or []

            print(f"\nKnowledge review: {normalized}")
            print(f"  Items: {len(items)}")
            print(f"  Overrides: {len(overrides)}")
            print(f"  Entity key field: {key_field}")

            while True:
                try:
                    command = input(
                        "\nAction [set/delete/delete-entity/list/quit]: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nCancelled.")
                    return

                if command in {"q", "quit", "exit", ""}:
                    return

                if command == "list":
                    if not items:
                        print("No extracted items for this category.")
                        continue
                    for item in items:
                        key_value = item.get(key_field)
                        print(f"  - {key_value}")
                    continue

                if command == "set":
                    entity_key = input(f"{key_field}: ").strip()
                    field_name = input("Field name: ").strip()
                    value = input("Override value: ").strip()
                    if not entity_key or not field_name:
                        print("Error: Entity key and field name are required.")
                        continue
                    submit_override(conn, normalized, entity_key, field_name, value)
                    conn.commit()
                    print("✓ Override saved.")
                    continue

                if command == "delete":
                    entity_key = input(f"{key_field}: ").strip()
                    field_name = input("Field name: ").strip()
                    if not entity_key or not field_name:
                        print("Error: Entity key and field name are required.")
                        continue
                    deleted = delete_knowledge_override(conn, normalized, entity_key, field_name)
                    conn.commit()
                    if deleted:
                        print("✓ Override deleted.")
                    else:
                        print("No override found.")
                    continue

                if command == "delete-entity":
                    entity_key = input(f"{key_field}: ").strip()
                    if not entity_key:
                        print("Error: Entity key is required.")
                        continue
                    try:
                        confirm = input(
                            f"Delete entity '{entity_key}'? This cannot be undone. [y/N]: "
                        ).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print("\nCancelled.")
                        return
                    if confirm == "y":
                        delete_knowledge_entity(conn, normalized, entity_key)
                        print(f"✓ Entity '{entity_key}' deleted. Run 'knowledge refresh' to re-extract.")
                    else:
                        print("Cancelled.")
                    continue

                print("Unknown action. Use set, delete, delete-entity, list, or quit.")
        finally:
            conn.close()

    elif action == "export":
        conn = get_connection(project_path)
        try:
            markdown = export_knowledge_markdown(conn)
        finally:
            conn.close()

        output_raw = (getattr(args, "output", None) or "").strip()
        output_path = Path(output_raw) if output_raw else (project_path / "KNOWLEDGE_EXPORT.md")
        output_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        print(f"✓ Exported knowledge markdown to {output_path}")


def cmd_scenes(args):
    """Manage scene projections."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    action = args.scenes_action

    if action == "list":
        refresh_result = ensure_project_knowledge_fresh(project_path)
        if refresh_result.get("refreshed"):
            print(
                "Refreshed project knowledge projections "
                f"(scenes updated: {refresh_result.get('scene_updated', 0)}, "
                f"indexes updated: {refresh_result.get('index_updated', 0)})."
            )

        rows = list_scene_projections(project_path)
        if not rows:
            print("No scene projections found.")
            return

        print(f"\n{'Scene ID':<18}  {'Scene Path':<44}  {'Last Refreshed'}")
        print("-" * 92)
        for row in rows:
            scene_id = row.get("scene_id") or "-"
            scene_path = row.get("scene_path") or "?"
            refreshed = (row.get("last_refreshed_at") or "?")[:19]
            print(f"{scene_id:<18}  {scene_path:<44}  {refreshed}")

    elif action == "lock":
        conn = get_connection(project_path)
        try:
            ExtractionStore.lock_scene(conn, args.scene_filename)
        finally:
            conn.close()
        print(f"Locked scene for extraction: {args.scene_filename}")

    elif action == "unlock":
        conn = get_connection(project_path)
        try:
            ExtractionStore.unlock_scene(conn, args.scene_filename)
        finally:
            conn.close()
        print(f"Unlocked scene for extraction: {args.scene_filename}")

    elif action == "rename":
        conn = get_connection(project_path)
        try:
            result = rename_scene(
                project_path=project_path,
                old_filename=args.old_filename,
                new_filename=args.new_filename,
                conn=conn,
            )
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except FileExistsError as e:
            print(f"Error: {e}")
            sys.exit(1)
        finally:
            conn.close()

        print(f"Renamed scene: {result['old_scene']} -> {result['new_scene']}")
        print(f"Updated scene files: {len(result['updated_scene_files'])}")
        print(f"Updated session rows: {result['updated_session_rows']}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="lit-critic",
        description="Multi-lens editorial review system for fiction manuscripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Focus Areas:\n"
            "  Knowledge: refresh, review, export\n"
            "  Scenes:   list, lock, unlock, rename\n"
            "  Sessions: start, resume, list, show, delete\n"
            "\n"
            "Examples:\n"
            "  lit-critic sessions start --scene X --project Y --mode quick\n"
            "  lit-critic sessions resume --project Y\n"
            "  lit-critic knowledge refresh --project Y\n"
            "  lit-critic scenes list --project Y\n"
            "  lit-critic scenes lock text/ch01.md --project Y\n"
            "  lit-critic scenes rename text/ch01.md text/ch01-rev.md --project Y"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    model_choices = sorted(get_available_models().keys())

    # --- analyze ---
    # DEPRECATED ALIAS
    p_analyze = subparsers.add_parser(
        "analyze",
        help=argparse.SUPPRESS,
    )
    p_analyze.add_argument("--scene", required=True, help="Path to the scene file")
    p_analyze.add_argument("--project", required=True, help="Path to the project directory")
    p_analyze.add_argument("--api-key", help="API key (or set env var)")
    p_analyze.add_argument(
        "--mode",
        choices=["quick", "deep"],
        default="deep",
        help="Sessions/Analyze mode: quick or deep (default: deep).",
    )

    # --- config ---
    p_config = subparsers.add_parser("config", help="Manage model-slot configuration")
    sp_config = p_config.add_subparsers(dest="config_action", required=True)

    sp_config.add_parser("show", help="Show resolved model-slot configuration")
    sp_config_set = sp_config.add_parser("set", help="Set one or more model-slot assignments")
    sp_config_set.add_argument(
        "assignments",
        nargs="+",
        help="Slot assignments like frontier=opus deep=sonnet quick=haiku",
    )

    # --- sessions ---
    p_sessions = subparsers.add_parser("sessions", help="Manage sessions")
    sp_sessions = p_sessions.add_subparsers(dest="sessions_action", required=True)

    sp_start = sp_sessions.add_parser("start", help="Start a new analysis session")
    sp_start.add_argument("--scene", required=True, help="Path to the scene file")
    sp_start.add_argument("--project", required=True, help="Path to the project directory")
    sp_start.add_argument("--api-key", help="API key (or set env var)")
    sp_start.add_argument(
        "--mode",
        choices=["quick", "deep"],
        default="deep",
        help="Sessions start mode: quick or deep (default: deep).",
    )

    sp_resume = sp_sessions.add_parser("resume", help="Resume an active session")
    sp_resume.add_argument("--project", required=True)
    sp_resume.add_argument("--api-key", help="API key (or set env var)")

    sp_list = sp_sessions.add_parser("list", help="List all sessions")
    sp_list.add_argument("--project", required=True)

    sp_show = sp_sessions.add_parser("show", help="Show session details")
    sp_show.add_argument("id", type=int, help="Session ID")
    sp_show.add_argument("--project", required=True)

    sp_delete = sp_sessions.add_parser("delete", help="Delete a session")
    sp_delete.add_argument("id", type=int, help="Session ID")
    sp_delete.add_argument("--project", required=True)

    # --- resume ---
    # DEPRECATED ALIAS
    p_resume = subparsers.add_parser("resume", help=argparse.SUPPRESS)
    p_resume.add_argument("--project", required=True, help="Path to the project directory")
    p_resume.add_argument("--api-key", help="API key (or set env var)")

    # --- learning ---
    p_learning = subparsers.add_parser("learning", help="Manage learning data")
    sp_learning = p_learning.add_subparsers(dest="learning_action", required=True)

    sp_llist = sp_learning.add_parser("list", help="List learning data")
    sp_llist.add_argument("--project", required=True)

    sp_ladd = sp_learning.add_parser("add", help="Add a learning entry (interactive)")
    sp_ladd.add_argument("--project", required=True)

    sp_lupdate = sp_learning.add_parser("update", help="Update a learning entry")
    sp_lupdate.add_argument("id", type=int, help="Learning entry ID")
    sp_lupdate.add_argument("--project", required=True)

    sp_lexport = sp_learning.add_parser("export", help="Export LEARNING.md")
    sp_lexport.add_argument("--project", required=True)

    sp_lreset = sp_learning.add_parser("reset", help="Reset all learning data")
    sp_lreset.add_argument("--project", required=True)

    # --- knowledge ---
    p_knowledge = subparsers.add_parser("knowledge", help="Manage knowledge refresh/review/export")
    sp_knowledge = p_knowledge.add_subparsers(dest="knowledge_action", required=True)

    sp_knowledge_refresh = sp_knowledge.add_parser(
        "refresh",
        help="Refresh scene/index projections and extracted knowledge",
    )
    sp_knowledge_refresh.add_argument("--project", required=True)

    sp_knowledge_review = sp_knowledge.add_parser(
        "review",
        help="Interactively review extracted knowledge for a category",
    )
    sp_knowledge_review.add_argument("category", nargs="?", help="Category (characters|terms|threads|timeline|scene_metadata)")
    sp_knowledge_review.add_argument("--project", required=True)

    sp_knowledge_export = sp_knowledge.add_parser(
        "export",
        help="Export extracted knowledge markdown",
    )
    sp_knowledge_export.add_argument("--project", required=True)
    sp_knowledge_export.add_argument(
        "--output",
        help="Output markdown file path (default: <project>/KNOWLEDGE_EXPORT.md)",
    )

    # --- scenes ---
    p_scenes = subparsers.add_parser("scenes", help="Manage scene projections")
    sp_scenes = p_scenes.add_subparsers(dest="scenes_action", required=True)

    sp_scenes_list = sp_scenes.add_parser("list", help="List scene projections")
    sp_scenes_list.add_argument("--project", required=True)

    sp_scenes_lock = sp_scenes.add_parser("lock", help="Lock a scene from auto-extraction")
    sp_scenes_lock.add_argument("scene_filename", help="Project-relative scene path")
    sp_scenes_lock.add_argument("--project", required=True)

    sp_scenes_unlock = sp_scenes.add_parser("unlock", help="Unlock a scene for auto-extraction")
    sp_scenes_unlock.add_argument("scene_filename", help="Project-relative scene path")
    sp_scenes_unlock.add_argument("--project", required=True)

    sp_scenes_rename = sp_scenes.add_parser("rename", help="Rename a scene and propagate references")
    sp_scenes_rename.add_argument("old_filename", help="Current project-relative scene path")
    sp_scenes_rename.add_argument("new_filename", help="New project-relative scene path")
    sp_scenes_rename.add_argument("--project", required=True)

    # --- session (focus-area alias group) ---
    p_session = subparsers.add_parser("session", help="Sessions focus-area commands")
    sp_session = p_session.add_subparsers(dest="session_action", required=True)

    sp_session_analyze = sp_session.add_parser("analyze", help="Analyze a scene")
    sp_session_analyze.add_argument("--scene", required=True, help="Path to the scene file")
    sp_session_analyze.add_argument("--project", required=True, help="Path to the project directory")
    sp_session_analyze.add_argument("--api-key", help="API key (or set env var)")
    sp_session_analyze.add_argument(
        "--mode",
        choices=["quick", "deep"],
        default="deep",
        help="Analysis depth mode: quick or deep (default: deep).",
    )

    sp_session_refresh = sp_session.add_parser(
        "refresh",
        help="Refresh an active session after index changes",
    )
    sp_session_refresh.add_argument("--project", required=True, help="Path to the project directory")
    sp_session_refresh.add_argument("--api-key", help="API key (or set env var)")

    sp_session_config = sp_session.add_parser("config", help="Manage model-slot configuration")
    sp_session_config_actions = sp_session_config.add_subparsers(
        dest="session_config_action",
        required=True,
    )
    sp_session_config_actions.add_parser("show", help="Show resolved model-slot configuration")
    sp_session_config_set = sp_session_config_actions.add_parser(
        "set",
        help="Set one or more model-slot assignments",
    )
    sp_session_config_set.add_argument(
        "assignments",
        nargs="+",
        help="Slot assignments like frontier=opus deep=sonnet quick=haiku",
    )

    return parser


def _normalize_focus_area_aliases(args) -> None:
    """Map focus-area alias commands to existing command handlers."""
    if args.command == "analyze":
        args.command = "sessions"
        args.sessions_action = "start"

    if args.command == "resume":
        args.command = "sessions"
        args.sessions_action = "resume"

    if args.command == "session":
        if args.session_action == "analyze":
            args.command = "sessions"
            args.sessions_action = "start"
        elif args.session_action == "refresh":
            args.command = "sessions"
            args.sessions_action = "resume"
        elif args.session_action == "config":
            args.command = "config"
            args.config_action = args.session_config_action

async def main():
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    _normalize_focus_area_aliases(args)

    if args.command == 'sessions' and args.sessions_action in {'start', 'resume'}:
        try:
            _ensure_repo_path_preflight()
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)

    if args.command == 'config':
        cmd_config(args)
    elif args.command == 'sessions':
        await cmd_sessions(args)
    elif args.command == 'learning':
        cmd_learning(args)
    elif args.command == 'knowledge':
        cmd_knowledge(args)
    elif args.command == 'scenes':
        cmd_scenes(args)
