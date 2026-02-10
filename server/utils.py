"""
Utility functions for the lit-critic system.

Provides:
- Line numbering for scene text (enabling line-number-aware locations)
- Diff-based line mapping for scene change detection
- Finding line adjustment after edits
"""

import difflib
from typing import Optional

from .models import Finding


def number_lines(text: str) -> str:
    """Prepend line numbers to each line of text.

    Format: ``L001: first line``, ``L002: second line``, etc.
    The width of the number is determined by the total number of lines
    so that all prefixes align.

    This is used in prompts so that Claude can see and reference line numbers.
    """
    lines = text.split('\n')
    width = max(len(str(len(lines))), 3)
    return '\n'.join(
        f"L{i + 1:0{width}d}: {line}"
        for i, line in enumerate(lines)
    )


# ---------------------------------------------------------------------------
# Diff-based line mapping
# ---------------------------------------------------------------------------

def compute_line_mapping(old_text: str, new_text: str) -> dict:
    """Compute how line numbers shifted between two versions of a text.

    Uses ``difflib.SequenceMatcher`` to align old and new lines.

    Returns a dict with:
        mapping  – ``{old_line: new_line}`` for lines that survived unchanged
                   (1-based line numbers on both sides).
        deleted  – ``set`` of old line numbers that were deleted or replaced.
        inserted – ``set`` of new line numbers that are entirely new.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    mapping: dict[int, int] = {}
    deleted: set[int] = set()
    inserted: set[int] = set()

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1  # 1-based
        elif tag == 'delete':
            for i in range(i1, i2):
                deleted.add(i + 1)
        elif tag == 'replace':
            for i in range(i1, i2):
                deleted.add(i + 1)
            for j in range(j1, j2):
                inserted.add(j + 1)
        elif tag == 'insert':
            for j in range(j1, j2):
                inserted.add(j + 1)

    return {"mapping": mapping, "deleted": deleted, "inserted": inserted}


def adjust_finding_lines(finding: Finding, line_mapping: dict) -> str:
    """Adjust a finding's ``line_start`` / ``line_end`` using a line mapping.

    Returns a status string:
        ``"adjusted"`` – lines shifted successfully to new positions.
        ``"stale"``    – finding's line range overlaps an edited/deleted region;
                         the finding needs re-evaluation.
        ``"no_lines"`` – finding has no line numbers (cannot adjust).
    """
    if finding.line_start is None:
        return "no_lines"

    mapping = line_mapping["mapping"]
    deleted = line_mapping["deleted"]

    end = finding.line_end if finding.line_end is not None else finding.line_start
    finding_lines = range(finding.line_start, end + 1)

    # If any line in the finding's range was deleted/replaced, it's stale
    if any(line in deleted for line in finding_lines):
        finding.stale = True
        return "stale"

    # Try to map both endpoints
    new_start = mapping.get(finding.line_start)
    new_end = mapping.get(end)

    if new_start is None:
        finding.stale = True
        return "stale"

    finding.line_start = new_start
    finding.line_end = new_end if finding.line_end is not None else None
    return "adjusted"


def apply_scene_change(findings: list[Finding], old_text: str, new_text: str,
                       start_index: int = 0) -> dict:
    """Detect a scene change and adjust all remaining findings.

    Computes the diff between *old_text* and *new_text*, then adjusts
    ``line_start``/``line_end`` for every finding from *start_index* onward
    that has not already been processed (i.e. status is ``"pending"`` or any
    active status).

    Returns a summary dict:
        adjusted  – number of findings whose lines were shifted
        stale     – number of findings marked stale (need re-evaluation)
        no_lines  – number of findings without line numbers
        total     – total findings examined
    """
    line_mapping = compute_line_mapping(old_text, new_text)

    summary = {"adjusted": 0, "stale": 0, "no_lines": 0, "total": 0}

    for finding in findings[start_index:]:
        summary["total"] += 1
        result = adjust_finding_lines(finding, line_mapping)
        summary[result] += 1

    return summary
