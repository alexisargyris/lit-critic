"""
CLI interface and main entry point for the lit-critic system.
"""

import argparse
import os
import sys
from pathlib import Path

from server.config import (
    INDEX_FILES, OPTIONAL_FILES, SESSION_FILE,
    AVAILABLE_MODELS, DEFAULT_MODEL, API_KEY_ENV_VARS,
    resolve_model, resolve_api_key,
)
from server.llm import create_client
from server.models import SessionState, Finding, LearningData, CoordinatorError
from server.learning import load_learning, save_learning_to_file
from server.session import (
    session_exists, save_session, load_session, delete_session,
    validate_session, get_session_file_path, detect_and_apply_scene_changes
)
from server.discussion import handle_discussion, handle_discussion_stream
from server.api import run_analysis


def load_project_files(project_path: Path) -> dict[str, str]:
    """Load all index files from the project directory."""
    indexes = {}
    
    for filename in INDEX_FILES:
        filepath = project_path / filename
        if filepath.exists():
            indexes[filename] = filepath.read_text(encoding='utf-8')
            print(f"  ✓ Loaded {filename}")
        else:
            print(f"  ✗ Missing {filename}")
            indexes[filename] = ""
    
    for filename in OPTIONAL_FILES:
        filepath = project_path / filename
        if filepath.exists():
            indexes[filename] = filepath.read_text(encoding='utf-8')
            print(f"  ✓ Loaded {filename} (optional)")
    
    return indexes


def load_scene(scene_path: Path) -> str:
    """Load the scene file."""
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")
    return scene_path.read_text(encoding='utf-8')


def print_summary(results: dict):
    """Print the editorial summary."""
    print("\n" + "=" * 60)
    print("GLOSSARY CHECK")
    print("=" * 60)
    
    glossary_issues = results.get("glossary_issues", [])
    if glossary_issues:
        for issue in glossary_issues:
            print(f"  • {issue}")
    else:
        print("  All terms match GLOSSARY.md. No issues.")
    
    print("\n" + "=" * 60)
    print("EDITORIAL SUMMARY")
    print("=" * 60)
    
    summary = results.get("summary", {})
    prose = summary.get("prose", {})
    structure = summary.get("structure", {})
    coherence = summary.get("coherence", {})
    
    print(f"  PROSE:     {prose.get('critical', 0)} critical, {prose.get('major', 0)} major, {prose.get('minor', 0)} minor")
    print(f"  STRUCTURE: {structure.get('critical', 0)} critical, {structure.get('major', 0)} major, {structure.get('minor', 0)} minor")
    print(f"  COHERENCE: {coherence.get('critical', 0)} critical, {coherence.get('major', 0)} major, {coherence.get('minor', 0)} minor")
    
    conflicts = results.get("conflicts", [])
    ambiguities = results.get("ambiguities", [])
    
    print(f"\n  Conflicts between lenses: {len(conflicts)}")
    print(f"  Ambiguities requiring clarification: {len(ambiguities)}")
    
    print("\n" + "=" * 60)
    print("Ready for discussion. Type 'continue' to begin.")
    print("Commands: continue | skip minor | skip to structure | skip to coherence")
    print("          reject | accept | save learning | quit | help")
    print("=" * 60)


def print_finding_revision(finding):
    """Print what changed when a finding was revised or escalated."""
    if not finding.revision_history:
        return
    old = finding.revision_history[-1]
    if old.get("severity") != finding.severity:
        print(f"  Severity: {old['severity']} → {finding.severity}")
    if old.get("evidence") != finding.evidence:
        print(f"  Evidence: {finding.evidence}")
    if old.get("impact") != finding.impact:
        print(f"  Impact: {finding.impact}")
    if old.get("options") != finding.options:
        print("  Options:")
        for i, opt in enumerate(finding.options, 1):
            print(f"    {i}. {opt}")


def print_finding(finding: dict, current: int = None, total: int = None):
    """Print a single finding in the standard format."""
    print("\n" + "-" * 60)
    header = f"FINDING #{finding.get('number', '?')} — {finding.get('severity', '?').upper()} — {finding.get('lens', '?').upper()}"
    if current is not None and total is not None:
        progress = f"[{current} of {total}]"
        # Calculate padding to right-align the progress indicator
        padding = 60 - len(header) - len(progress) - 1
        if padding > 0:
            header = header + " " * padding + progress
        else:
            header = header + "  " + progress
    print(header)
    print("-" * 60)
    
    # Show location with line range
    location = finding.get('location', 'Not specified')
    line_start = finding.get('line_start')
    line_end = finding.get('line_end')
    if line_start and not any(f"L{line_start}" in location for _ in [1]):
        line_ref = f"L{line_start}" + (f"-L{line_end}" if line_end and line_end != line_start else "")
        location = f"{location}  ({line_ref})"
    print(f"\nLocation: {location}")

    if finding.get('stale'):
        print("  ⚠ [STALE — text in this region was edited, finding may be outdated]")
    print(f"\nEvidence: {finding.get('evidence', 'Not specified')}")
    print(f"\nImpact: {finding.get('impact', 'Not specified')}")
    
    print("\nOptions:")
    for i, option in enumerate(finding.get('options', []), 1):
        print(f"  {i}. {option}")
    
    flagged_by = finding.get('flagged_by', [])
    if len(flagged_by) > 1:
        print(f"\n[Flagged by multiple lenses: {', '.join(flagged_by)}]")
    
    if finding.get('ambiguity_type') == 'ambiguous_possibly_intentional':
        print("\n[This may be intentional ambiguity. Please clarify: 'intentional' or 'accidental']")
    
    print("\n" + "-" * 60)


async def run_interactive_session(state: SessionState, results: dict = None, 
                                   start_index: int = 0, initial_skip_minor: bool = False):
    """Run the interactive discussion session.
    
    Args:
        state: The session state
        results: Analysis results (None if resuming from saved session)
        start_index: Finding index to start from (for resume)
        initial_skip_minor: Whether to skip minor findings (for resume)
    """
    
    # Convert results to Finding objects if provided (new session)
    if results is not None:
        findings_data = results.get("findings", [])
        state.findings = [
            Finding(
                number=f.get('number', i+1),
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
        state.glossary_issues = results.get("glossary_issues", [])
    
    if not state.findings:
        print("\nNo findings to discuss. The scene looks good!")
        # Delete session file if review completed
        delete_session(state.project_path)
        return
    
    current = start_index
    skip_minor = initial_skip_minor
    skip_to_lens = None
    session_completed = False
    
    # Show resume info
    if start_index > 0:
        processed = len([f for f in state.findings[:start_index] if f.status != "pending"])
        print(f"\n[Resuming session: {processed} findings processed, starting at #{start_index + 1}]")
    
    while current < len(state.findings):
        # --- Scene change detection (before each finding transition) ---
        change_report = await detect_and_apply_scene_changes(state, current)
        if change_report:
            print(f"\n  ⟳ Scene file changed.")
            print(f"    • {change_report['adjusted']} findings adjusted (line numbers shifted)")
            if change_report['stale'] > 0:
                print(f"    • {change_report['stale']} findings marked stale (text was rewritten)")
                re_results = change_report.get('re_evaluated', [])
                if re_results:
                    print(f"    Re-evaluating stale findings against updated scene...")
                    for r in re_results:
                        if r['status'] == 'updated':
                            print(f"      ✓ Finding #{r['finding_number']}: updated (still valid)")
                        elif r['status'] == 'withdrawn':
                            print(f"      ✓ Finding #{r['finding_number']}: withdrawn ({r.get('reason', 'edit resolved it')})")
                        elif r['status'] == 'error':
                            print(f"      ⚠ Finding #{r['finding_number']}: re-evaluation failed ({r.get('error', 'unknown')})")
            if change_report.get('no_lines', 0) > 0:
                print(f"    • {change_report['no_lines']} findings have no line numbers (unchanged)")

        finding = state.findings[current]

        # Skip withdrawn findings (may have been withdrawn by re-evaluation)
        if finding.status == 'withdrawn':
            current += 1
            continue
        
        # Handle skip conditions
        if skip_minor and finding.severity.lower() == 'minor':
            current += 1
            continue
            
        if skip_to_lens:
            lens = finding.lens.lower()
            if skip_to_lens == 'structure' and lens == 'prose':
                current += 1
                continue
            elif skip_to_lens == 'coherence' and lens in ['prose', 'structure']:
                current += 1
                continue
            skip_to_lens = None
        
        total_findings = len(state.findings)
        print_finding(finding.to_dict(), current + 1, total_findings)
        
        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nSession ended.")
                return
            
            user_lower = user_input.lower()
            
            # Navigation commands
            if user_lower in ['continue', 'c', '']:
                current += 1
                break
            elif user_lower == 'skip minor':
                skip_minor = True
                current += 1
                break
            elif user_lower == 'skip to structure':
                skip_to_lens = 'structure'
                current += 1
                break
            elif user_lower == 'skip to coherence':
                skip_to_lens = 'coherence'
                current += 1
                break
            elif user_lower in ['quit', 'q', 'exit']:
                # Offer to save session if there are remaining findings
                if current < len(state.findings):
                    try:
                        save_choice = input("\nSave session for later? (y/n): ").strip().lower()
                        if save_choice in ['y', 'yes']:
                            filepath = save_session(state, current, skip_minor)
                            print(f"  ✓ Session saved to {filepath}")
                            print(f"  Resume with: --resume --project {state.project_path}")
                            # Check if this is the first time saving
                            print(f"\n  Tip: Add '{SESSION_FILE}' to your project's .gitignore")
                    except (EOFError, KeyboardInterrupt):
                        pass
                print("\nSession ended.")
                return
            
            # Quick accept/reject
            elif user_lower == 'accept':
                finding.status = 'accepted'
                state.learning.session_acceptances.append({
                    "lens": finding.lens,
                    "pattern": finding.evidence[:100]
                })
                print("\n[Finding accepted. Moving to next.]")
                current += 1
                break
            elif user_lower == 'reject':
                reason = input("Reason (brief): ").strip()
                finding.status = 'rejected'
                finding.author_response = reason
                state.learning.session_rejections.append({
                    "lens": finding.lens,
                    "pattern": finding.evidence[:100],
                    "reason": reason
                })
                print("\n[Finding rejected. Moving to next.]")
                current += 1
                break
            
            # Ambiguity classification
            elif user_lower == 'intentional' and finding.ambiguity_type:
                state.learning.session_ambiguity_answers.append({
                    "location": finding.location,
                    "description": finding.evidence[:100],
                    "intentional": True
                })
                print("\n[Marked as intentional ambiguity. Moving to next.]")
                current += 1
                break
            elif user_lower == 'accidental' and finding.ambiguity_type:
                state.learning.session_ambiguity_answers.append({
                    "location": finding.location,
                    "description": finding.evidence[:100],
                    "intentional": False
                })
                print("\n[Marked as accidental confusion. Moving to next.]")
                current += 1
                break
            
            # Learning commands
            elif user_lower == 'save learning':
                filepath = save_learning_to_file(state.learning, state.project_path)
                print(f"\n  ✓ Saved to {filepath}")
            
            # Session commands
            elif user_lower == 'save session':
                filepath = save_session(state, current, skip_minor)
                print(f"\n  ✓ Session saved to {filepath}")
                print(f"  Resume with: --resume --project {state.project_path}")
            
            elif user_lower == 'clear session':
                if delete_session(state.project_path):
                    print("\n  ✓ Session file deleted")
                else:
                    print("\n  No saved session found")
            
            elif user_lower == 'help':
                print("\nCommands:")
                print("  continue (c, Enter) - next finding")
                print("  accept             - accept finding, move on")
                print("  reject             - reject finding (prompts for reason)")
                print("  skip minor         - skip all minor findings")
                print("  skip to structure  - jump to structure findings")
                print("  skip to coherence  - jump to coherence findings")
                print("  intentional        - mark ambiguity as intentional")
                print("  accidental         - mark ambiguity as accidental")
                print("  save learning      - save LEARNING.md to project directory")
                print("  save session       - save progress to resume later")
                print("  clear session      - delete saved session file")
                print("  quit (q)           - end session (offers to save)")
                print("  [any other text]   - discuss with critic")
            
            # Discussion - any other input (streamed token-by-token)
            else:
                print("\n[Discussing with critic...]")
                print("\nCritic: ", end="", flush=True)
                response = ""
                status = "continue"
                async for chunk_type, data in handle_discussion_stream(state, finding, user_input):
                    if chunk_type == "token":
                        print(data, end="", flush=True)
                    elif chunk_type == "done":
                        response = data["response"]
                        status = data["status"]
                print()  # newline after streaming
                
                if status == 'accepted':
                    finding.status = 'accepted'
                    print("\n[Finding accepted. Type 'continue' to proceed.]")
                elif status == 'rejected' or status == 'conceded':
                    finding.status = 'rejected'
                    print("\n[Finding dismissed. Type 'continue' to proceed.]")
                elif status == 'revised':
                    finding.status = 'revised'
                    print("\n[Finding revised by critic:]")
                    print_finding_revision(finding)
                    print("\n[Type 'continue' to proceed, or keep discussing.]")
                elif status == 'withdrawn':
                    finding.status = 'withdrawn'
                    print("\n[Finding withdrawn by critic. Moving to next.]")
                    current += 1
                    break
                elif status == 'escalated':
                    finding.status = 'escalated'
                    print("\n[Finding escalated by critic:]")
                    print_finding_revision(finding)
                    print("\n[Type 'continue' to proceed, or keep discussing.]")
    
    print("\n" + "=" * 60)
    print("All findings have been presented.")
    print("Type 'save learning' to save LEARNING.md, or 'quit' to exit.")
    print("=" * 60)
    
    # Final prompt for save learning
    while True:
        try:
            final_input = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        
        if final_input == 'save learning':
            filepath = save_learning_to_file(state.learning, state.project_path)
            print(f"\n  ✓ Saved to {filepath}")
        elif final_input in ['quit', 'q', 'exit', '']:
            break


async def main():
    parser = argparse.ArgumentParser(description="lit-critic - Multi-lens editorial review")
    parser.add_argument("--scene", help="Path to the scene file (required unless --resume)")
    parser.add_argument("--project", required=True, help="Path to the project directory containing index files")
    parser.add_argument("--api-key", help="API key for the model provider (or set ANTHROPIC_API_KEY / OPENAI_API_KEY env var)")
    parser.add_argument("--model", choices=list(AVAILABLE_MODELS.keys()), default=DEFAULT_MODEL,
                        help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--resume", action="store_true", help="Resume a previously saved session")
    
    args = parser.parse_args()
    
    # Resolve model and provider
    model_cfg = resolve_model(args.model)
    provider = model_cfg["provider"]
    
    # Get API key for the provider
    try:
        api_key = resolve_api_key(provider, args.api_key)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Initialize provider-agnostic client
    try:
        client = create_client(provider, api_key)
    except (ValueError, ImportError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Load project path
    print("\nLoading project files...")
    project_path = Path(args.project)
    if not project_path.exists():
        print(f"Error: Project directory not found: {project_path}")
        sys.exit(1)
    
    indexes = load_project_files(project_path)
    
    # Handle resume mode
    if args.resume:
        print("\nChecking for saved session...")
        session_data = load_session(project_path)
        
        if not session_data:
            print("Error: No saved session found in project directory.")
            print(f"  Expected: {get_session_file_path(project_path)}")
            sys.exit(1)
        
        # Get scene path from session
        scene_path_str = session_data.get("scene_path", "")
        if not scene_path_str:
            print("Error: Session file is corrupted (missing scene path)")
            sys.exit(1)
        
        scene_path = Path(scene_path_str)
        print(f"  ✓ Found saved session for: {scene_path.name}")
        print(f"  ✓ Saved at: {session_data.get('saved_at', 'unknown')}")
        
        # Load scene
        print("\nLoading scene...")
        try:
            scene = load_scene(scene_path)
            print(f"  ✓ Loaded {scene_path.name} ({len(scene)} characters)")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        # Validate session
        is_valid, error_msg = validate_session(session_data, scene, str(scene_path))
        if not is_valid:
            print(f"Error: Cannot resume session - {error_msg}")
            print("  Start a new review with --scene instead, or delete the session file.")
            sys.exit(1)
        
        # Load learning data
        print("\nLoading learning data...")
        learning = load_learning(project_path)
        
        # Restore session learning state
        learning_session = session_data.get("learning_session", {})
        learning.session_rejections = learning_session.get("session_rejections", [])
        learning.session_acceptances = learning_session.get("session_acceptances", [])
        learning.session_ambiguity_answers = learning_session.get("session_ambiguity_answers", [])
        
        print(f"  ✓ Review count: {learning.review_count}")
        print(f"  ✓ Preferences: {len(learning.preferences)}")
        
        # Restore model from session (fall back to CLI arg, then default)
        saved_model = session_data.get("model", args.model)
        if saved_model not in AVAILABLE_MODELS:
            print(f"  Warning: Saved model '{saved_model}' no longer available, using {args.model}")
            saved_model = args.model
        
        model_cfg = resolve_model(saved_model)
        print(f"  ✓ Model: {saved_model} ({model_cfg['id']})")
        
        # Create session state with restored data
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
        )
        
        # Get resume position
        start_index = session_data.get("current_index", 0)
        skip_minor = session_data.get("skip_minor", False)
        
        print(f"\n  ✓ Resuming from finding #{start_index + 1} of {len(state.findings)}")
        
        # Run interactive session from saved position
        print("\n" + "=" * 60)
        print("RESUMING SESSION")
        print("=" * 60)
        await run_interactive_session(state, results=None, start_index=start_index, 
                                       initial_skip_minor=skip_minor)
        
        # Delete session file on completion
        delete_session(project_path)
        
    else:
        # Normal mode - require scene
        if not args.scene:
            print("Error: --scene is required unless resuming a session with --resume")
            sys.exit(1)
        
        print("\nLoading scene...")
        scene_path = Path(args.scene)
        try:
            scene = load_scene(scene_path)
            print(f"  ✓ Loaded {scene_path.name} ({len(scene)} characters)")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        # Check for existing session
        if session_exists(project_path):
            existing_session = load_session(project_path)
            if existing_session:
                existing_scene = existing_session.get("scene_path", "unknown")
                print(f"\nWarning: Found existing session for: {existing_scene}")
                try:
                    choice = input("Discard existing session and start fresh? (y/n): ").strip().lower()
                    if choice not in ['y', 'yes']:
                        print("Hint: Use --resume to continue the existing session.")
                        sys.exit(0)
                    delete_session(project_path)
                except (EOFError, KeyboardInterrupt):
                    sys.exit(0)
        
        # Load learning data
        print("\nLoading learning data...")
        learning = load_learning(project_path)
        print(f"  ✓ Review count: {learning.review_count}")
        print(f"  ✓ Preferences: {len(learning.preferences)}")
        print(f"  ✓ Blind spots: {len(learning.blind_spots)}")
        
        # Resolve model
        model_cfg = resolve_model(args.model)
        print(f"  ✓ Model: {args.model} ({model_cfg['id']})")
        
        # Create session state
        state = SessionState(
            client=client,
            scene_content=scene,
            scene_path=str(scene_path),
            project_path=project_path,
            indexes=indexes,
            learning=learning,
            model=args.model,
        )
        
        # Run analysis
        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)
        
        try:
            results = await run_analysis(client, scene, indexes,
                                         model=state.model_id, max_tokens=state.model_max_tokens)
        except CoordinatorError as e:
            print(f"\nError during coordination: {e}")
            if e.raw_output:
                print(f"Raw output: {e.raw_output[:500]}...")
            if e.attempts > 1:
                print(f"(failed after {e.attempts} attempts)")
            sys.exit(1)
        
        # Print summary and run interactive session
        print_summary(results)
        await run_interactive_session(state, results)
        
        # Delete session file on successful completion
        delete_session(project_path)
