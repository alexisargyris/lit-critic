"""
Display helpers and shared utilities for the lit-critic CLI.

Contains formatting functions used by both the interactive session loop
and the subcommand implementations.
"""

from pathlib import Path

from lit_platform.facade import PlatformFacade
from lit_platform.services.analysis_service import INDEX_FILES, OPTIONAL_FILES


def load_project_files(project_path: Path) -> dict[str, str]:
    """Load all index files from the project directory."""
    indexes = PlatformFacade.load_legacy_indexes_from_project(
        project_path,
        optional_filenames=tuple(OPTIONAL_FILES),
    )

    for filename in INDEX_FILES:
        if indexes.get(filename):
            print(f"  ✓ Loaded {filename}")
        else:
            print(f"  ✗ Missing {filename}")
            indexes[filename] = ""

    for filename in OPTIONAL_FILES:
        if indexes.get(filename):
            print(f"  ✓ Loaded {filename} (optional)")

    return indexes


def load_scene(scene_path: Path) -> str:
    """Load the scene file."""
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")
    return PlatformFacade.load_scene_text(scene_path)


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
    print("Commands: continue | review | skip to structure | skip to coherence")
    print("          (coherence = logic + clarity + continuity + dialogue)")
    print("          reject | accept | export learning | quit | help")
    print("=" * 60)


def print_finding(finding: dict, current: int = None, total: int = None):
    """Print a single finding in the standard format."""
    print("\n" + "-" * 60)
    header = (
        f"FINDING #{finding.get('number', '?')} — "
        f"{finding.get('severity', '?').upper()} — "
        f"{finding.get('lens', '?').upper()}"
    )
    if current is not None and total is not None:
        progress = f"[{current} of {total}]"
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
    if line_start and f"L{line_start}" not in location:
        line_ref = f"L{line_start}"
        if line_end and line_end != line_start:
            line_ref += f"-L{line_end}"
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


def print_scene_change_report(change_report: dict) -> None:
    """Print a scene-change detection report."""
    print(f"\n  ⟳ Scene file changed.")
    print(f"    • {change_report['adjusted']} findings adjusted (line numbers shifted)")
    if change_report['stale'] > 0:
        print(f"    • {change_report['stale']} findings marked stale (text was rewritten)")
        re_results = change_report.get('re_evaluated', [])
        if re_results:
            print("    Re-evaluating stale findings against updated scene...")
            for r in re_results:
                if r['status'] == 'updated':
                    print(f"      ✓ Finding #{r['finding_number']}: updated (still valid)")
                elif r['status'] == 'withdrawn':
                    reason = r.get('reason', 'edit resolved it')
                    print(f"      ✓ Finding #{r['finding_number']}: withdrawn ({reason})")
                elif r['status'] == 'error':
                    error = r.get('error', 'unknown')
                    print(f"      ⚠ Finding #{r['finding_number']}: re-evaluation failed ({error})")
    no_lines = change_report.get('no_lines', 0)
    if no_lines > 0:
        print(f"    • {no_lines} findings have no line numbers (unchanged)")
