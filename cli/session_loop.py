"""
Interactive session loop for the lit-critic CLI.

Handles the finding-by-finding review loop with auto-save to SQLite.
Every action (accept, reject, discuss, navigate) is persisted immediately.
"""

from lit_platform.session_state_machine import (
    apply_acceptance,
    apply_discussion_status,
    apply_rejection,
    first_unresolved_index,
    next_available_index,
    next_index_for_lens,
    record_ambiguity_answer,
)
from lit_platform.persistence import LearningStore

from lit_platform.services import (
    detect_and_apply_scene_changes,
    review_current_finding_against_scene_edits,
    persist_finding,
    persist_session_index,
    persist_session_learning,
    persist_discussion_history,
    complete_session,
    create_session,
    discuss_finding_stream,
    export_learning_markdown,
)
from lit_platform.models import SessionState, Finding

from .interface import (
    print_finding,
    print_finding_revision,
    print_scene_change_report,
)


async def run_interactive_session(
    state: SessionState,
    results: dict = None,
    start_index: int = 0,
):
    """Run the interactive discussion session with auto-save.

    Args:
        state: The session state (must have db_conn/session_id set, or
               will be populated when *results* is provided).
        results: Analysis results (None if resuming from saved session).
        start_index: Finding index to start from (for resume).
    """

    # Convert results to Finding objects if provided (new session)
    if results is not None:
        findings_data = results.get("findings", [])
        state.findings = [
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
                ambiguity_type=f.get('ambiguity_type'),
            )
            for i, f in enumerate(findings_data)
        ]
        state.glossary_issues = results.get("glossary_issues", [])

        # Create session in DB (auto-save from this point on)
        session_id = create_session(state, state.glossary_issues)
        print(f"  [Session #{session_id} created — all progress auto-saved]")

    if not state.findings:
        print("\nNo findings to discuss. The scene looks good!")
        complete_session(state)
        return

    current = start_index

    # Show resume info
    if start_index > 0:
        processed = sum(
            1 for f in state.findings[:start_index] if f.status != "pending"
        )
        print(f"\n[Resuming: {processed} findings processed, starting at #{start_index + 1}]")

    while current < len(state.findings):
        current = next_available_index(state.findings, current)
        if current >= len(state.findings):
            break

        # --- Scene change detection ---
        change_report = await detect_and_apply_scene_changes(state, current)
        if change_report:
            print_scene_change_report(change_report)

        finding = state.findings[current]

        total_findings = len(state.findings)
        print_finding(finding.to_dict(), current + 1, total_findings)

        # --- Inner command loop for this finding ---
        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nSession paused (auto-saved).")
                return

            user_lower = user_input.lower()

            # Navigation
            if user_lower in ('continue', 'c', ''):
                current += 1
                persist_session_index(state, current)
                break

            elif user_lower == 'review':
                review_report = await review_current_finding_against_scene_edits(state, current)
                if review_report.get("changed"):
                    print_scene_change_report(review_report)
                else:
                    print(f"\n[Review] {review_report.get('message', 'No scene changes detected.')}")
                # Re-render the current finding after review/re-evaluation.
                print_finding(state.findings[current].to_dict(), current + 1, total_findings)

            elif user_lower == 'skip to structure':
                current = next_index_for_lens(state.findings, current, 'structure')
                persist_session_index(state, current)
                break

            elif user_lower == 'skip to coherence':
                current = next_index_for_lens(state.findings, current, 'coherence')
                persist_session_index(state, current)
                break

            elif user_lower in ('quit', 'q', 'exit'):
                print("\nSession paused (auto-saved). Resume anytime with:")
                print(f"  lit-critic resume --project {state.project_path}")
                return

            # Accept
            elif user_lower == 'accept':
                apply_acceptance(finding, state.learning)
                persist_finding(state, finding)
                persist_session_learning(state)
                print("\n[Finding accepted. Moving to next.]")
                current += 1
                persist_session_index(state, current)
                break

            # Reject
            elif user_lower == 'reject':
                reason = input("Reason (brief): ").strip()
                apply_rejection(finding, state.learning, reason)
                persist_finding(state, finding)
                persist_session_learning(state)
                print("\n[Finding rejected. Moving to next.]")
                current += 1
                persist_session_index(state, current)
                break

            # Ambiguity
            elif user_lower == 'intentional' and finding.ambiguity_type:
                record_ambiguity_answer(
                    finding,
                    state.learning,
                    intentional=True,
                )
                persist_session_learning(state)
                print("\n[Marked as intentional ambiguity. Moving to next.]")
                current += 1
                persist_session_index(state, current)
                break

            elif user_lower == 'accidental' and finding.ambiguity_type:
                record_ambiguity_answer(
                    finding,
                    state.learning,
                    intentional=False,
                )
                persist_session_learning(state)
                print("\n[Marked as accidental confusion. Moving to next.]")
                current += 1
                persist_session_index(state, current)
                break

            # Export learning (file-only export from DB — learning is already saved)
            elif user_lower == 'export learning':
                filepath = export_learning_markdown(state.project_path)
                print(f"\n  ✓ Exported to {filepath}")

            # Help
            elif user_lower == 'help':
                _print_help()

            # Discussion — any other input
            else:
                await _handle_discussion(state, finding, user_input)
                current_status = finding.status
                if current_status == 'withdrawn':
                    current += 1
                    persist_session_index(state, current)
                    break

    # Reached the end of the current traversal.
    # Only complete when every finding has a terminal outcome.
    if not complete_session(state):
        unresolved = first_unresolved_index(state.findings)
        if unresolved is None:
            print("\nSession paused: unresolved findings remain.")
            return

        print("\n[There are still pending findings. Returning to the first unresolved one.]")
        persist_session_index(state, unresolved)
        await run_interactive_session(
            state,
            results=None,
            start_index=unresolved,
        )
        return

    # Increment review count once per completed session.
    if state.db_conn:
        LearningStore.increment_review_count(state.db_conn)
        state.learning.review_count += 1  # keep in-memory state in sync

    prefs = len(state.learning.preferences)
    amb = len(state.learning.ambiguity_intentional) + len(state.learning.ambiguity_accidental)
    print("\n" + "=" * 60)
    print("All findings have been considered. Session completed.")
    print(f"  Learning updated: {prefs} preference(s), {amb} ambiguity pattern(s) in DB.")
    print("Type 'export learning' to write LEARNING.md, or 'quit' to exit.")
    print("=" * 60)

    while True:
        try:
            final_input = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if final_input == 'export learning':
            filepath = export_learning_markdown(state.project_path)
            print(f"\n  ✓ Exported to {filepath}")
        elif final_input in ('quit', 'q', 'exit', ''):
            break


async def _handle_discussion(state: SessionState, finding: Finding,
                             user_input: str) -> None:
    """Stream a discussion exchange and apply the result."""
    print("\n[Discussing with critic...]")
    print("\nCritic: ", end="", flush=True)

    response = ""
    status = "continue"

    async for chunk_type, data in discuss_finding_stream(state, finding, user_input):
        if chunk_type == "token":
            print(data, end="", flush=True)
        elif chunk_type == "done":
            response = data["response"]
            status = data["status"]
    print()  # newline after streaming

    # Apply canonical discussion status mapping and print UX message.
    apply_discussion_status(finding, status)
    if finding.status == 'accepted':
        print("\n[Finding accepted. Type 'continue' to proceed.]")
    elif finding.status == 'rejected':
        print("\n[Finding dismissed. Type 'continue' to proceed.]")
    elif finding.status == 'withdrawn':
        if status == 'conceded':
            print("\n[Finding conceded by critic. Moving to next.]")
        else:
            print("\n[Finding withdrawn by critic. Moving to next.]")
    elif finding.status == 'revised':
        print("\n[Finding revised by critic:]")
        print_finding_revision(finding)
        print("\n[Type 'continue' to proceed, or keep discussing.]")
    elif finding.status == 'escalated':
        print("\n[Finding escalated by critic:]")
        print_finding_revision(finding)
        print("\n[Type 'continue' to proceed, or keep discussing.]")

    # Auto-save finding and discussion history
    persist_finding(state, finding)
    persist_discussion_history(state)
    persist_session_learning(state)


def _print_help():
    """Print available commands."""
    print("\nCommands:")
    print("  continue (c, Enter) - next finding")
    print("  accept             - accept finding, move on")
    print("  reject             - reject finding (prompts for reason)")
    print("  review             - re-check current finding against scene edits")
    print("  skip to structure  - jump to structure findings")
    print("  skip to coherence  - jump to coherence findings")
    print("  intentional        - mark ambiguity as intentional")
    print("  accidental         - mark ambiguity as accidental")
    print("  export learning    - export LEARNING.md to project directory")
    print("  quit (q)           - pause session (auto-saved)")
    print("  [any other text]   - discuss with critic")
