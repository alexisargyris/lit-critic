"""
CLI subcommand implementations for the lit-critic system.

Subcommands::

    lit-critic analyze  --scene X --project Y [--model M] [--api-key K]
    lit-critic resume   --project Y [--api-key K]
    lit-critic sessions list   --project Y
    lit-critic sessions view   ID --project Y
    lit-critic sessions delete ID --project Y
    lit-critic learning view   --project Y
    lit-critic learning export --project Y
    lit-critic learning reset  --project Y
"""

import argparse
import os
import sys
from pathlib import Path

from lit_platform.repo_preflight import MARKER_FILENAME, validate_repo_path
from lit_platform.user_config import get_repo_path, set_repo_path
from lit_platform.session_state_machine import restore_learning_session
from lit_platform.models import SessionState, Finding, CoordinatorError
from lit_platform.services.analysis_service import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    LENS_PRESETS,
    create_client,
    normalize_lens_preferences,
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
from lit_platform.persistence import SessionStore

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
# Subcommand: analyze
# ---------------------------------------------------------------------------

async def cmd_analyze(args):
    lens_overrides = {}
    for item in args.lens_weight or []:
        if '=' not in item:
            print(f"Error: Invalid --lens-weight '{item}'. Expected format lens=weight (e.g. prose=1.3)")
            sys.exit(1)
        lens_name, raw_weight = item.split('=', 1)
        lens_name = lens_name.strip().lower()
        raw_weight = raw_weight.strip()
        try:
            lens_overrides[lens_name] = float(raw_weight)
        except ValueError:
            print(f"Error: Invalid weight '{raw_weight}' for lens '{lens_name}'.")
            sys.exit(1)

    try:
        lens_preferences = normalize_lens_preferences(
            {
                "preset": args.lens_preset,
                "weights": lens_overrides,
            }
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

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

    # Resolve model and API key
    model_cfg = resolve_model(args.model)
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
    discussion_model = None
    discussion_client = None
    discussion_model_cfg = None
    if args.discussion_model:
        discussion_model = args.discussion_model
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
    print(f"  ✓ Analysis model: {args.model} ({model_cfg['id']})")
    if discussion_model:
        print(f"  ✓ Discussion model: {discussion_model} ({discussion_model_cfg['id']})")
    print(f"  ✓ Lens preset: {lens_preferences['preset']}")

    # Create session state
    state = SessionState(
        client=client,
        scene_content=scene,
        scene_path=str(scene_path),
        project_path=project_path,
        indexes=indexes,
        learning=learning,
        lens_preferences=lens_preferences,
        model=args.model,
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
            lens_preferences=state.lens_preferences,
        )
    except CoordinatorError as e:
        print(f"\nError during coordination: {e}")
        if e.raw_output:
            print(f"Raw output: {e.raw_output[:500]}...")
        if e.attempts > 1:
            print(f"(failed after {e.attempts} attempts)")
        sys.exit(1)

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
    if saved_model not in AVAILABLE_MODELS:
        print(f"  Warning: Model '{saved_model}' unavailable, using {DEFAULT_MODEL}")
        saved_model = DEFAULT_MODEL

    model_cfg = resolve_model(saved_model)
    provider = model_cfg["provider"]
    print(f"  ✓ Analysis model: {saved_model} ({model_cfg['id']})")

    # Restore discussion model if present in session
    saved_discussion_model = session_data.get("discussion_model")
    if saved_discussion_model and saved_discussion_model not in AVAILABLE_MODELS:
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
        lens_preferences=session_data.get("lens_preferences") or normalize_lens_preferences(None),
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
# Subcommand: sessions
# ---------------------------------------------------------------------------

def cmd_sessions(args):
    """Manage saved sessions."""
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)

    action = args.sessions_action

    if action == 'list':
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

    elif action == 'view':
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

    if action == 'view':
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


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="lit-critic",
        description="Multi-lens editorial review system for fiction manuscripts",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = subparsers.add_parser("analyze", help="Run a new analysis")
    p_analyze.add_argument("--scene", required=True, help="Path to the scene file")
    p_analyze.add_argument("--project", required=True, help="Path to the project directory")
    p_analyze.add_argument("--api-key", help="API key (or set env var)")
    p_analyze.add_argument(
        "--model", choices=list(AVAILABLE_MODELS.keys()),
        default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})",
    )
    p_analyze.add_argument(
        "--discussion-model", choices=list(AVAILABLE_MODELS.keys()),
        default=None, help="Model for discussion (default: same as analysis model)",
    )
    p_analyze.add_argument(
        "--lens-preset",
        choices=sorted(LENS_PRESETS.keys()),
        default="balanced",
        help="Lens weighting preset (default: balanced)",
    )
    p_analyze.add_argument(
        "--lens-weight",
        action="append",
        help="Override individual lens weight, format lens=weight (repeatable)",
    )

    # --- resume ---
    p_resume = subparsers.add_parser("resume", help="Resume an active session")
    p_resume.add_argument("--project", required=True, help="Path to the project directory")
    p_resume.add_argument("--api-key", help="API key (or set env var)")

    # --- sessions ---
    p_sessions = subparsers.add_parser("sessions", help="Manage sessions")
    sp_sessions = p_sessions.add_subparsers(dest="sessions_action", required=True)

    sp_list = sp_sessions.add_parser("list", help="List all sessions")
    sp_list.add_argument("--project", required=True)

    sp_view = sp_sessions.add_parser("view", help="View session details")
    sp_view.add_argument("id", type=int, help="Session ID")
    sp_view.add_argument("--project", required=True)

    sp_delete = sp_sessions.add_parser("delete", help="Delete a session")
    sp_delete.add_argument("id", type=int, help="Session ID")
    sp_delete.add_argument("--project", required=True)

    # --- learning ---
    p_learning = subparsers.add_parser("learning", help="Manage learning data")
    sp_learning = p_learning.add_subparsers(dest="learning_action", required=True)

    sp_lview = sp_learning.add_parser("view", help="View learning data")
    sp_lview.add_argument("--project", required=True)

    sp_lexport = sp_learning.add_parser("export", help="Export LEARNING.md")
    sp_lexport.add_argument("--project", required=True)

    sp_lreset = sp_learning.add_parser("reset", help="Reset all learning data")
    sp_lreset.add_argument("--project", required=True)

    return parser


async def main():
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {'analyze', 'resume'}:
        try:
            _ensure_repo_path_preflight()
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)

    if args.command == 'analyze':
        await cmd_analyze(args)
    elif args.command == 'resume':
        await cmd_resume(args)
    elif args.command == 'sessions':
        cmd_sessions(args)
    elif args.command == 'learning':
        cmd_learning(args)
