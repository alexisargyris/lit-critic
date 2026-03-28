"""Index file automation service.

Scans a scene via LLM and inserts draft entries into
CAST.md, GLOSSARY.md, THREADS.md, and TIMELINE.md.

Strategy
--------
- LLM proposes new entries using the extract_index_entries tool.
- For each proposal, check if it already exists in the target file.
- **New** entries are inserted **inline** at the end of the appropriate section,
  so the author doesn't need to move content around.
- **Existing** entries whose ID already appears in the file are **reconciled**:
  unique information from either the old or the new entry is preserved, and
  when both entries contain the same field, the newer (LLM-proposed) value
  wins — unless the new value is a ``[TODO]`` placeholder, in which case the
  existing real value is kept.
- A small ``<!-- ⚡ auto: SCENE_ID -->`` marker is added to each auto-inserted
  entry so the author can find and review them (e.g. via Ctrl+F "⚡ auto").
- Existing threads that were advanced/closed are noted in the report so
  the author can update them manually.
"""

import collections
import json
import os
import re
from pathlib import Path

from lit_platform.persistence.database import get_connection
from lit_platform.runtime.api import run_index_extraction
from lit_platform.runtime.config import DEFAULT_MODEL, MAX_TOKENS
from lit_platform.services.audit_service import audit_indexes_deterministic

# ---------------------------------------------------------------------------
# Target section headers
# ---------------------------------------------------------------------------

CAST_SECTION_BY_CATEGORY = {
    "main":       "## Main Characters",
    "supporting": "## Supporting Characters",
    "minor":      "## Minor Characters",
}

GLOSSARY_SECTION_BY_CATEGORY = {
    "term":  "## Terms",
    "place": "## Place Names",
}

THREADS_NEW_SECTION = "## Active Threads"

# Marker comment appended to auto-generated entries (searchable)
_AUTO_MARKER_PREFIX = "<!-- ⚡ auto:"

# Matches a field header line such as:
#   - **Age:** 24         (CAST style, with leading dash)
#   **Definition:** text  (GLOSSARY/THREADS style, no dash)
_FIELD_HEADER_RE = re.compile(r'^(?:\s*-\s*)?\*\*([^*:]+):\*\*\s*(.*)$')

# Fields whose values should always be preserved from the *old* entry.
# These represent provenance / first-occurrence information that must not be
# overwritten by a later scan.
_IMMUTABLE_FIELDS = frozenset({"opened", "first seen", "first_seen"})

_INDEX_PREFLIGHT_ENV = "LIT_CRITIC_INDEX_PREFLIGHT_AUDIT"


def _index_preflight_enabled() -> bool:
    """Return True when deterministic index preflight is explicitly enabled."""
    raw = os.environ.get(_INDEX_PREFLIGHT_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scan_scene_for_index_entries(
    scene_content: str,
    project_path: Path,
    indexes: dict[str, str],
    client,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """Scan a scene and insert/reconcile entries in index files.

    Parameters
    ----------
    scene_content:
        Full text of the scene file (including @@META header).
    project_path:
        Root directory of the novel project (where index files live).
    indexes:
        Already-loaded index file contents keyed by filename (e.g. ``"CAST.md"``).
        Used both as context for the LLM and for duplicate detection.
    client:
        LLM client instance (``LLMClient``).
    model / max_tokens:
        LLM settings to use for extraction.

    Returns
    -------
    A report dict::

        {
            "scene_id": "01.03.01",
            "cast":     {"added": [...names], "skipped": [...names], "reconciled": [...names]},
            "glossary": {"added": [...terms], "skipped": [...terms], "reconciled": [...terms]},
            "threads":  {"added": [...ids], "advanced": [...ids], "closed": [...ids],
                         "reconciled": [...ids]},
            "timeline": {"added": [...ids], "skipped": [...ids], "reconciled": [...ids]},
            "error":    "<message>"   # only present on LLM failure
        }
    """
    scene_id = _extract_scene_id(scene_content)

    report: dict = {
        "scene_id": scene_id,
        "cast":     {"added": [], "skipped": [], "reconciled": []},
        "glossary": {"added": [], "skipped": [], "reconciled": []},
        "threads":  {"added": [], "advanced": [], "closed": [], "reconciled": []},
        "timeline": {"added": [], "skipped": [], "reconciled": []},
    }

    # Optional deterministic index-audit preflight (non-blocking).
    if _index_preflight_enabled():
        try:
            preflight_report = audit_indexes_deterministic(indexes)
            preflight_count = len(preflight_report.deterministic)
            if preflight_count > 0:
                report["preflight_warning"] = (
                    "Index preflight audit found "
                    f"{preflight_count} deterministic issue(s); scan will continue."
                )
                report["preflight_findings_count"] = preflight_count
        except Exception as e:
            report["preflight_warning"] = f"Index preflight audit failed (non-blocking): {e}"

    # Ask the LLM what's new
    proposed = await run_index_extraction(
        client, scene_content, indexes, model=model, max_tokens=max_tokens,
    )

    if "error" in proposed:
        report["error"] = proposed["error"]
        return report

    # ---- CAST.md -----------------------------------------------------------
    cast_path = project_path / "CAST.md"
    cast_content = cast_path.read_text(encoding="utf-8") if cast_path.exists() else ""
    cast_modified = cast_content
    cast_changed = False

    for entry in proposed.get("cast", []):
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        # Prepare draft before duplicate check so it is available for reconciliation
        category = entry.get("category", "supporting")
        draft = (entry.get("draft_entry") or "").strip()
        if not draft:
            draft = _default_cast_entry(name, scene_id)

        if _already_exists(name, cast_content):
            existing = _extract_existing_entry(cast_modified, name)
            if existing:
                reconciled = _reconcile_entries(existing, draft)
                if reconciled != existing:
                    cast_modified = _replace_entry_in_content(cast_modified, existing, reconciled)
                    cast_changed = True
                    report["cast"]["reconciled"].append(name)
                    continue
            report["cast"]["skipped"].append(name)
            continue

        # Genuinely new entry
        draft = _stamp_auto_marker(draft, scene_id)
        section = CAST_SECTION_BY_CATEGORY.get(category, CAST_SECTION_BY_CATEGORY["supporting"])
        cast_modified = _insert_into_section(cast_modified, section, draft)
        cast_changed = True
        report["cast"]["added"].append(name)

    if cast_changed:
        cast_path.write_text(cast_modified, encoding="utf-8")

    # ---- GLOSSARY.md -------------------------------------------------------
    glossary_path = project_path / "GLOSSARY.md"
    glossary_content = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""
    glossary_modified = glossary_content
    glossary_changed = False

    for entry in proposed.get("glossary", []):
        term = (entry.get("term") or "").strip()
        if not term:
            continue

        category = entry.get("category", "term")
        draft = (entry.get("draft_entry") or "").strip()
        if not draft:
            definition = (entry.get("definition") or "[TODO]").strip()
            draft = _default_glossary_entry(term, definition, scene_id)

        if _already_exists(term, glossary_content):
            existing = _extract_existing_entry(glossary_modified, term)
            if existing:
                reconciled = _reconcile_entries(existing, draft)
                if reconciled != existing:
                    glossary_modified = _replace_entry_in_content(glossary_modified, existing, reconciled)
                    glossary_changed = True
                    report["glossary"]["reconciled"].append(term)
                    continue
            report["glossary"]["skipped"].append(term)
            continue

        # Genuinely new entry
        draft = _stamp_auto_marker(draft, scene_id)
        section = GLOSSARY_SECTION_BY_CATEGORY.get(category, GLOSSARY_SECTION_BY_CATEGORY["term"])
        glossary_modified = _insert_into_section(glossary_modified, section, draft)
        glossary_changed = True
        report["glossary"]["added"].append(term)

    if glossary_changed:
        glossary_path.write_text(glossary_modified, encoding="utf-8")

    # ---- THREADS.md --------------------------------------------------------
    threads_path = project_path / "THREADS.md"
    threads_content = threads_path.read_text(encoding="utf-8") if threads_path.exists() else ""
    threads_modified = threads_content
    threads_changed = False

    for entry in proposed.get("threads", []):
        thread_id = (entry.get("thread_id") or "").strip()
        if not thread_id:
            continue
        action = entry.get("action", "new")
        draft = (entry.get("draft_entry") or "").strip()

        if action == "new":
            if not draft:
                draft = _default_thread_entry(thread_id, scene_id)

            if _already_exists(thread_id, threads_content):
                existing = _extract_existing_entry(threads_modified, thread_id)
                if existing:
                    reconciled = _reconcile_entries(existing, draft)
                    if reconciled != existing:
                        threads_modified = _replace_entry_in_content(threads_modified, existing, reconciled)
                        threads_changed = True
                        report["threads"]["reconciled"].append(thread_id)
                        continue
                # Could not reconcile — fall back to noting it as advanced
                report["threads"]["advanced"].append(thread_id)
                continue

            draft = _stamp_auto_marker(draft, scene_id)
            threads_modified = _insert_into_section(threads_modified, THREADS_NEW_SECTION, draft)
            threads_changed = True
            report["threads"]["added"].append(thread_id)

        elif action == "advanced":
            report["threads"]["advanced"].append(thread_id)

        elif action == "closed":
            report["threads"]["closed"].append(thread_id)

    if threads_changed:
        threads_path.write_text(threads_modified, encoding="utf-8")

    # ---- TIMELINE.md -------------------------------------------------------
    timeline_path = project_path / "TIMELINE.md"
    timeline_content = timeline_path.read_text(encoding="utf-8") if timeline_path.exists() else ""
    timeline_modified = timeline_content
    timeline_changed = False

    for entry in proposed.get("timeline", []):
        entry_scene_id = (entry.get("scene_id") or scene_id or "").strip()
        if not entry_scene_id:
            continue

        draft = (entry.get("draft_entry") or "").strip()
        if not draft:
            summary = (entry.get("summary") or "[TODO — outcome summary]").strip()
            draft = f"**{entry_scene_id}** {summary}"

        if _already_exists(entry_scene_id, timeline_content):
            existing = _extract_existing_entry(timeline_modified, entry_scene_id)
            if existing:
                reconciled = _reconcile_entries(existing, draft)
                if reconciled != existing:
                    timeline_modified = _replace_entry_in_content(timeline_modified, existing, reconciled)
                    timeline_changed = True
                    report["timeline"]["reconciled"].append(entry_scene_id)
                    continue
            report["timeline"]["skipped"].append(entry_scene_id)
            continue

        part = (entry.get("part") or "").strip()
        chapter = (entry.get("chapter") or "").strip()

        # Infer part/chapter from scene_id if not provided
        if (not part or not chapter) and entry_scene_id:
            parts = entry_scene_id.split(".")
            if len(parts) >= 2:
                part = part or parts[0].zfill(2)
                chapter = chapter or parts[1].zfill(2)

        timeline_modified = _insert_timeline_entry(
            timeline_modified, draft, part, chapter, entry_scene_id,
        )
        timeline_changed = True
        report["timeline"]["added"].append(entry_scene_id)

    if timeline_changed:
        timeline_path.write_text(timeline_modified, encoding="utf-8")

    return report


def get_index_coverage_gaps(
    project_path: Path,
    *,
    session_start_id: int | None = None,
    session_end_id: int | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """Report index entries never referenced by reviewed scenes in a session range.

    The result is deterministic:

    - reviewed scenes are ordered by ascending session id then first-seen path order
    - index entries are returned sorted by ``(scope, entry.lower())``
    - rows are source-attributed with source file, section, and heading line
    """
    normalized_scopes = _normalize_index_coverage_scopes(scopes)
    reviewed_scene_paths = _load_reviewed_scene_paths(
        project_path,
        session_start_id=session_start_id,
        session_end_id=session_end_id,
    )

    scene_text_by_path: dict[str, str] = {}
    missing_scene_paths: list[str] = []
    for scene_path in reviewed_scene_paths:
        resolved_path = Path(scene_path)
        if not resolved_path.is_absolute():
            resolved_path = project_path / resolved_path
        try:
            scene_text_by_path[scene_path] = resolved_path.read_text(encoding="utf-8")
        except OSError:
            missing_scene_paths.append(scene_path)

    indexed_entries: list[dict] = []
    if "cast" in normalized_scopes:
        indexed_entries.extend(_extract_index_entries(project_path / "CAST.md", scope="cast"))
    if "glossary" in normalized_scopes:
        indexed_entries.extend(_extract_index_entries(project_path / "GLOSSARY.md", scope="glossary"))

    indexed_entries.sort(key=lambda row: (row["scope"], row["entry"].lower(), row["entry"]))

    rows: list[dict] = []
    for entry in indexed_entries:
        pattern = _entry_reference_pattern(entry["entry"])
        matched_scene_paths = [
            scene_path
            for scene_path in reviewed_scene_paths
            if scene_path in scene_text_by_path and pattern.search(scene_text_by_path[scene_path])
        ]
        if matched_scene_paths:
            continue
        rows.append(
            {
                "scope": entry["scope"],
                "entry": entry["entry"],
                "source_file": entry["source_file"],
                "source_section": entry["source_section"],
                "source_line": entry["source_line"],
                "referenced_scene_paths": [],
            }
        )

    return {
        "filters": {
            "session_start_id": session_start_id,
            "session_end_id": session_end_id,
            "scopes": list(normalized_scopes),
        },
        "summary": {
            "reviewed_scene_count": len(reviewed_scene_paths),
            "indexed_entry_count": len(indexed_entries),
            "gap_count": len(rows),
        },
        "reviewed_scene_paths": reviewed_scene_paths,
        "missing_scene_paths": missing_scene_paths,
        "rows": rows,
    }


def get_finding_index_context(
    project_path: Path,
    finding: dict,
    *,
    scopes: list[str] | None = None,
    max_matches_per_scope: int = 3,
) -> dict:
    """Return deterministic index-entry context relevant to a single finding.

    The first version is intentionally heuristic and lightweight: it scans
    finding text fields for exact heading references against CAST / GLOSSARY
    entries already present on disk.
    """
    normalized_scopes = _normalize_index_coverage_scopes(scopes)
    bounded_max = max(1, int(max_matches_per_scope))

    searchable_fields: list[tuple[str, str]] = []
    for key in ("location", "evidence", "impact", "author_response"):
        value = finding.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                searchable_fields.append((key, text))

    options = finding.get("options")
    if isinstance(options, list):
        option_text = "\n".join(str(option).strip() for option in options if str(option).strip())
        if option_text:
            searchable_fields.append(("options", option_text))

    indexed_entries: list[dict] = []
    if "cast" in normalized_scopes:
        indexed_entries.extend(_extract_index_entries(project_path / "CAST.md", scope="cast"))
    if "glossary" in normalized_scopes:
        indexed_entries.extend(_extract_index_entries(project_path / "GLOSSARY.md", scope="glossary"))
    indexed_entries.sort(key=lambda row: (row["scope"], row["entry"].lower(), row["entry"]))

    counts_by_scope: collections.Counter[str] = collections.Counter()
    rows: list[dict] = []
    for entry in indexed_entries:
        scope = entry["scope"]
        if counts_by_scope[scope] >= bounded_max:
            continue

        pattern = _entry_reference_pattern(entry["entry"])
        matched_fields = [
            field_name
            for field_name, field_text in searchable_fields
            if pattern.search(field_text)
        ]
        if not matched_fields:
            continue

        counts_by_scope[scope] += 1
        rows.append(
            {
                "scope": scope,
                "entry": entry["entry"],
                "source_file": entry["source_file"],
                "source_section": entry["source_section"],
                "source_line": entry["source_line"],
                "matched_fields": matched_fields,
            }
        )

    return {
        "filters": {
            "scopes": list(normalized_scopes),
            "max_matches_per_scope": bounded_max,
        },
        "summary": {
            "candidate_entry_count": len(indexed_entries),
            "match_count": len(rows),
        },
        "rows": rows,
    }


def format_report(report: dict) -> str:
    """Format an index scan report for display in the CLI or VS Code."""
    lines = []
    scene_id = report.get("scene_id") or "?"
    lines.append(f"\nIndex scan results for scene {scene_id}:\n")

    preflight_warning = report.get("preflight_warning")
    if preflight_warning:
        lines.append(f"  ⚠ {preflight_warning}")
        lines.append("")

    cast = report.get("cast", {})
    glossary = report.get("glossary", {})
    threads = report.get("threads", {})
    timeline = report.get("timeline", {})

    def _fmt_list(items: list[str]) -> str:
        return ", ".join(items) if items else "none"

    lines.append(f"  CAST.md:     {len(cast.get('added', []))} new entry/entries added")
    if cast.get("added"):
        lines.append(f"    Added:   {_fmt_list(cast['added'])}")
    if cast.get("reconciled"):
        lines.append(f"    Reconciled (updated with new info): {_fmt_list(cast['reconciled'])}")
    if cast.get("skipped"):
        lines.append(f"    Already present (no new info): {_fmt_list(cast['skipped'])}")

    lines.append(f"  GLOSSARY.md: {len(glossary.get('added', []))} new entry/entries added")
    if glossary.get("added"):
        lines.append(f"    Added:   {_fmt_list(glossary['added'])}")
    if glossary.get("reconciled"):
        lines.append(f"    Reconciled (updated with new info): {_fmt_list(glossary['reconciled'])}")
    if glossary.get("skipped"):
        lines.append(f"    Already present (no new info): {_fmt_list(glossary['skipped'])}")

    lines.append(f"  THREADS.md:  {len(threads.get('added', []))} new thread(s) added")
    if threads.get("added"):
        lines.append(f"    Added:   {_fmt_list(threads['added'])}")
    if threads.get("reconciled"):
        lines.append(f"    Reconciled (updated with new info): {_fmt_list(threads['reconciled'])}")
    if threads.get("advanced"):
        lines.append(f"    Advanced (update manually): {_fmt_list(threads['advanced'])}")
    if threads.get("closed"):
        lines.append(f"    Closed (move to Resolved manually): {_fmt_list(threads['closed'])}")

    lines.append(f"  TIMELINE.md: {len(timeline.get('added', []))} new entry/entries added")
    if timeline.get("reconciled"):
        lines.append(f"    Reconciled (updated with new info): {_fmt_list(timeline['reconciled'])}")
    if timeline.get("skipped"):
        lines.append(f"    Already present (no new info): {_fmt_list(timeline['skipped'])}")

    total_added = (
        len(cast.get("added", []))
        + len(glossary.get("added", []))
        + len(threads.get("added", []))
        + len(timeline.get("added", []))
    )
    total_reconciled = (
        len(cast.get("reconciled", []))
        + len(glossary.get("reconciled", []))
        + len(threads.get("reconciled", []))
        + len(timeline.get("reconciled", []))
    )
    needs_manual = threads.get("advanced", []) + threads.get("closed", [])

    if total_added > 0:
        lines.append(
            f"\n  ✓ {total_added} new stub entry/entries inserted."
            " Search '⚡ auto' to find them and fill in [TODO] placeholders."
        )
    if total_reconciled > 0:
        lines.append(
            f"  ✓ {total_reconciled} existing entry/entries reconciled with new information."
        )
    if total_added == 0 and total_reconciled == 0:
        lines.append("\n  ✓ No new entries found — index files are up to date.")

    if needs_manual:
        lines.append(
            f"  ℹ {len(needs_manual)} thread(s) need manual status update in THREADS.md."
        )

    if "error" in report:
        lines.append(f"\n  ⚠ LLM error: {report['error']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reconciliation helpers
# ---------------------------------------------------------------------------

def _extract_existing_entry(content: str, entry_id: str) -> str:
    """Find and extract an existing index entry from file content by its heading ID.

    Searches for a markdown heading (``### entry_id``) with optional auto-marker
    comment, or a bold timeline scene ID (``**01.03.01**``).

    Returns the entry text with trailing blank lines stripped, ready for a
    direct string-replace back into the file.  Returns an empty string if the
    entry is not found.
    """
    entry_id_lower = entry_id.lower().strip()
    lines = content.split("\n")
    is_timeline = bool(re.match(r"^\d+\.\d+\.\d+$", entry_id))

    start_line: int | None = None
    heading_level: int = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            # Strip auto-marker comment before comparing
            if "<!--" in heading_text:
                heading_text = heading_text[: heading_text.index("<!--")].strip()
            if heading_text.lower() == entry_id_lower:
                start_line = i
                heading_level = level
                break

        if is_timeline and re.match(r"^\*\*" + re.escape(entry_id) + r"\*\*", stripped):
            start_line = i
            heading_level = 0
            break

    if start_line is None:
        return ""

    # Find where this entry ends (exclusive)
    end_line = len(lines)

    if heading_level > 0:
        # End at the next heading at the same or higher level (fewer # chars)
        for i in range(start_line + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("#"):
                lvl = len(stripped) - len(stripped.lstrip("#"))
                if lvl <= heading_level:
                    end_line = i
                    break
    else:
        # Timeline inline entry: ends at the next heading or next bold scene ID
        for i in range(start_line + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped and (
                stripped.startswith("#")
                or re.match(r"^\*\*\d+\.\d+\.\d+\*\*", stripped)
            ):
                end_line = i
                break

    # Strip trailing blank lines so the extracted text can be found verbatim
    while end_line > start_line and not lines[end_line - 1].strip():
        end_line -= 1

    return "\n".join(lines[start_line:end_line])


def _parse_entry_into_blocks(
    entry_text: str,
) -> tuple[str, list[str], "collections.OrderedDict[str, list[str]]"]:
    """Parse a markdown index entry into its structural components.

    Returns a 3-tuple ``(heading_line, preamble_lines, field_blocks)`` where:

    * ``heading_line`` — the first line of the entry (e.g. ``### Alice``)
    * ``preamble_lines`` — any non-empty lines between the heading and the first
      detected ``**FieldName:**`` header.  This captures author-written prose
      that does not follow the template structure.
    * ``field_blocks`` — an :class:`~collections.OrderedDict` mapping the
      *normalised* (lowercase) field name to a list of lines comprising that
      field: ``[header_line, *sub_item_lines]``.
    """
    lines = entry_text.split("\n")
    heading_line = lines[0] if lines else ""

    blocks: collections.OrderedDict[str, list[str]] = collections.OrderedDict()
    preamble: list[str] = []
    current_key: str | None = None
    current_block: list[str] = []

    for line in lines[1:]:
        m = _FIELD_HEADER_RE.match(line.strip())
        if m:
            if current_key is not None:
                blocks[current_key] = _trim_trailing_blank_lines(current_block)
            current_key = m.group(1).strip().lower()
            current_block = [line]
        elif current_key is None:
            preamble.append(line)
        else:
            current_block.append(line)

    if current_key is not None:
        blocks[current_key] = _trim_trailing_blank_lines(current_block)

    return heading_line, _trim_trailing_blank_lines(preamble), blocks


def _reconcile_entries(old_entry: str, new_entry: str) -> str:
    """Merge two index entries with "new wins on conflict" semantics.

    Rules:

    * Fields present only in the **old** entry are preserved unchanged.
    * Fields present only in the **new** entry are appended.
    * When both entries contain the same field:

      - If the old value is a ``[TODO]`` placeholder → use the new value.
      - If the new value is a ``[TODO]`` placeholder → keep the old value.
      - For *immutable* provenance fields (``Opened``, ``First seen``) →
        always keep the old value regardless of placeholders.
      - Otherwise → the new value wins.

    * For list-style fields (sub-items beneath a field header) the union of
      sub-items is kept.  Items sharing the same key prefix (e.g. the same
      relationship target ``George:``) prefer the new description.

    * If either entry has no structured fields (e.g. a plain TIMELINE line
      like ``**01.03.01** summary``) and the new text is not a placeholder,
      the new text is returned directly.

    * On any parsing failure the function returns *old_entry* unchanged so
      the file is never corrupted.

    The heading line (``### Name``) is always taken from the *old* entry so
    that author-added auto-markers and manual edits to the heading are
    preserved.
    """
    try:
        old_heading, old_preamble, old_blocks = _parse_entry_into_blocks(old_entry)
        _new_heading, new_preamble, new_blocks = _parse_entry_into_blocks(new_entry)

        # Single-line entries with no field structure (e.g. timeline lines)
        if not old_blocks and not new_blocks and not old_preamble and not new_preamble:
            new_val = new_entry.strip()
            old_val = old_entry.strip()
            if new_val and not _is_placeholder(new_val) and new_val != old_val:
                return new_entry.rstrip()
            return old_entry.rstrip()

        # Prefer old preamble (may contain author prose not in template)
        result_preamble = old_preamble if old_preamble else new_preamble

        result_blocks: collections.OrderedDict[str, list[str]] = collections.OrderedDict()

        # Old fields first — preserving original ordering
        for key, old_block in old_blocks.items():
            if key in new_blocks:
                result_blocks[key] = _merge_field_block(old_block, new_blocks[key], key)
            else:
                result_blocks[key] = old_block

        # New-only fields appended after the old ones
        for key, new_block in new_blocks.items():
            if key not in result_blocks:
                result_blocks[key] = new_block

        # Reconstruct the entry
        result_lines = [old_heading]
        if result_preamble:
            result_lines.extend(result_preamble)
        for block in result_blocks.values():
            result_lines.extend(block)

        return "\n".join(result_lines).rstrip()

    except Exception:
        # Never corrupt the file — return the original unchanged
        return old_entry


def _replace_entry_in_content(
    content: str, old_entry_text: str, new_entry_text: str
) -> str:
    """Replace the first occurrence of *old_entry_text* with *new_entry_text*.

    Returns *content* unchanged if *old_entry_text* is not found (safety guard).
    """
    if not old_entry_text:
        return content
    if old_entry_text in content:
        return content.replace(old_entry_text, new_entry_text, 1)
    return content


# ---------------------------------------------------------------------------
# Reconciliation internals
# ---------------------------------------------------------------------------

def _trim_trailing_blank_lines(lines: list[str]) -> list[str]:
    """Return a copy of *lines* with trailing blank lines removed."""
    result = list(lines)
    while result and not result[-1].strip():
        result.pop()
    return result


def _extract_inline_value(header_line: str) -> str:
    """Extract the inline value portion from a field header line.

    For ``- **Age:** 24 (born Year 818 PA)`` returns ``"24 (born Year 818 PA)"``.
    Returns an empty string if the line does not match the field header pattern.
    """
    m = _FIELD_HEADER_RE.match(header_line.strip())
    return m.group(2).strip() if m else ""


def _is_placeholder(value: str) -> bool:
    """Return True if *value* is a ``[TODO]`` placeholder (in any form) or empty.

    Matches ``[TODO]``, ``[TODO — any note]``, ``[TODO: details]``, etc.
    The check is case-insensitive and looks for the opening ``[todo`` token so
    that em-dash variants like ``[TODO — outcome summary]`` are also recognised.
    """
    v = value.lower().strip()
    return not v or "[todo" in v


def _item_key_prefix(line: str) -> str | None:
    """Return the key prefix of a sub-item line, or ``None`` if it has none.

    Relationship lines like ``  - George: mentor, father-figure`` produce the
    key ``"george"``.  Bare fact lines like ``  - Fought in the war`` produce
    ``None``.  Only short (≤ 2-word, < 30-character) prefixes are treated as
    keys to avoid false-positive matching.
    """
    stripped = line.strip().lstrip("-").strip()
    if ":" not in stripped:
        return None
    candidate = stripped.split(":")[0].strip().lower()
    words = candidate.split()
    if 1 <= len(words) <= 2 and len(candidate) < 30:
        return candidate
    return None


def _merge_sub_items(old_subs: list[str], new_subs: list[str]) -> list[str]:
    """Merge two lists of sub-item lines.

    * All non-placeholder items from *new_subs* are included.
    * Items from *old_subs* whose key prefix (if any) is already covered by a
      new item are dropped.
    * Remaining old items that do not duplicate new content are appended.

    If the merged result would be empty, *old_subs* is returned as a fallback.
    """

    def _is_real(line: str) -> bool:
        return bool(line.strip()) and not _is_placeholder(line.strip().lstrip("-").strip())

    old_real = [ln for ln in old_subs if _is_real(ln)]
    new_real = [ln for ln in new_subs if _is_real(ln)]

    if not new_real and not old_real:
        return old_subs

    result: list[str] = []
    new_keys: set[str] = set()

    # New items first
    for line in new_real:
        result.append(line)
        key = _item_key_prefix(line)
        if key:
            new_keys.add(key)

    # Old items not superseded by new
    for line in old_real:
        key = _item_key_prefix(line)
        if key and key in new_keys:
            continue  # New version already included
        line_stripped = line.strip()
        if not any(line_stripped == r.strip() for r in result):
            result.append(line)

    return result if result else old_subs


def _merge_field_block(
    old_block: list[str], new_block: list[str], field_key: str = ""
) -> list[str]:
    """Merge two field blocks (each is ``[header_line, *sub_items]``).

    Immutable provenance fields (``Opened``, ``First seen``) always keep the
    old block.  For all other fields, the inline value is chosen according to
    placeholder rules (old wins if new is ``[TODO]``, new wins otherwise), and
    sub-items are unioned.
    """
    if field_key in _IMMUTABLE_FIELDS:
        return old_block

    old_header = old_block[0] if old_block else ""
    new_header = new_block[0] if new_block else ""
    old_subs = old_block[1:] if len(old_block) > 1 else []
    new_subs = new_block[1:] if len(new_block) > 1 else []

    old_value = _extract_inline_value(old_header)
    new_value = _extract_inline_value(new_header)

    # Choose the header line
    if _is_placeholder(old_value) and not _is_placeholder(new_value):
        chosen_header = new_header
    elif _is_placeholder(new_value) and not _is_placeholder(old_value):
        chosen_header = old_header
    elif new_value:
        chosen_header = new_header  # new wins on genuine overlap
    else:
        chosen_header = old_header

    if old_subs or new_subs:
        merged_subs = _merge_sub_items(old_subs, new_subs)
        return [chosen_header] + merged_subs

    return [chosen_header]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_scene_id(scene_content: str) -> str:
    """Extract scene ID from @@META header."""
    match = re.search(
        r"@@META.*?^ID:\s*(.+?)$",
        scene_content,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _normalize_index_coverage_scopes(scopes: list[str] | None) -> tuple[str, ...]:
    """Normalize optional coverage scopes to a deterministic tuple."""
    if scopes is None:
        return ("cast", "glossary")

    allowed = {"cast", "glossary"}
    normalized: list[str] = []
    for raw_scope in scopes:
        scope = (raw_scope or "").strip().lower()
        if not scope:
            continue
        if scope not in allowed:
            raise ValueError(f"Unsupported index coverage scope: {raw_scope}")
        if scope not in normalized:
            normalized.append(scope)

    return tuple(normalized or ("cast", "glossary"))


def _load_reviewed_scene_paths(
    project_path: Path,
    *,
    session_start_id: int | None,
    session_end_id: int | None,
) -> list[str]:
    """Load distinct reviewed scene paths in ascending session-id order."""
    clauses: list[str] = []
    params: list[int] = []

    if session_start_id is not None:
        clauses.append("id >= ?")
        params.append(session_start_id)
    if session_end_id is not None:
        clauses.append("id <= ?")
        params.append(session_end_id)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT id, scene_path FROM session {where_clause} ORDER BY id ASC"

    with get_connection(project_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    scene_paths: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for scene_path in _decode_session_scene_paths(row["scene_path"]):
            normalized_path = scene_path.strip()
            if not normalized_path or normalized_path in seen:
                continue
            seen.add(normalized_path)
            scene_paths.append(normalized_path)

    return scene_paths


def _decode_session_scene_paths(raw_scene_path: str | None) -> list[str]:
    """Decode session.scene_path into a list, preserving backward compatibility."""
    if raw_scene_path is None:
        return []
    value = raw_scene_path.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(decoded, list):
            return [str(item) for item in decoded if isinstance(item, str)]
    return [value]


def _extract_index_entries(index_path: Path, *, scope: str) -> list[dict]:
    """Extract level-3 heading entries from an index document."""
    if not index_path.exists():
        return []

    lines = index_path.read_text(encoding="utf-8").splitlines()
    section = ""
    entries: list[dict] = []

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            section = stripped[3:].strip()
            continue
        if not stripped.startswith("### "):
            continue

        entry = stripped[4:].strip()
        if "<!--" in entry:
            entry = entry.split("<!--", 1)[0].strip()
        if not entry:
            continue

        entries.append(
            {
                "scope": scope,
                "entry": entry,
                "source_file": index_path.name,
                "source_section": section,
                "source_line": line_no,
            }
        )

    return entries


def _entry_reference_pattern(entry: str) -> re.Pattern[str]:
    """Compile a conservative case-insensitive entry reference pattern."""
    escaped = re.escape(entry.strip())
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _already_exists(name: str, file_content: str) -> bool:
    """Return True if *name* already appears meaningfully in *file_content*.

    Checks common markdown heading and emphasis patterns, case-insensitively.
    Uses a word-boundary lookahead so a name like ``"Ali"`` does not spuriously
    match a heading ``"### Alice"``.
    Also handles scene IDs (01.03.01) and thread IDs (snake_case).
    """
    name_lower = name.lower().strip()
    content_lower = file_content.lower()

    # Markdown heading variations — require the name to be followed by whitespace,
    # end-of-string, or the start of an HTML comment (auto-marker), so that a
    # shorter name like "Ali" doesn't match inside "### Alice".
    heading_patterns = [
        f"### {name_lower}",
        f"## {name_lower}",
        f"**{name_lower}**",
    ]
    for pat in heading_patterns:
        if re.search(re.escape(pat) + r"(?=\s|$|<!--)", content_lower):
            return True

    # Scene IDs: check for literal occurrence (e.g. 01.03.01)
    if re.match(r"^\d+\.\d+\.\d+$", name):
        if name in file_content:
            return True

    # Thread IDs (snake_case): check literal occurrence
    if "_" in name and name == name.lower():
        if name_lower in content_lower:
            return True

    return False


def _stamp_auto_marker(draft: str, scene_id: str) -> str:
    """Add an auto marker comment to the heading line of *draft*."""
    if _AUTO_MARKER_PREFIX in draft:
        return draft  # already stamped

    lines = draft.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:  # first non-empty line
            marker = f"  {_AUTO_MARKER_PREFIX} {scene_id} -->" if scene_id else f"  {_AUTO_MARKER_PREFIX} -->"
            lines[i] = line.rstrip() + marker
            break
    return "\n".join(lines)


def _insert_into_section(content: str, section_header: str, new_entry: str) -> str:
    """Insert *new_entry* at the end of the named section in *content*.

    If the section heading is not found, appends to the end of the file.
    Cleans up excessive blank lines.
    """
    lines = content.split("\n")

    # Locate the section heading
    section_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == section_header),
        None,
    )

    if section_idx is None:
        # Section not found — append with a fallback block
        suffix = f"\n{section_header}\n\n{new_entry}\n"
        return content.rstrip() + "\n" + suffix

    # Determine the section's heading level from the leading # characters
    section_level = len(section_header) - len(section_header.lstrip("#"))

    # Find where this section ends (next heading at same or higher level)
    end_idx = len(lines)
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            current_level = len(stripped) - len(stripped.lstrip("#"))
            if current_level <= section_level:
                end_idx = i
                break

    # Find the last non-empty line within the section to insert after it
    insert_after = section_idx
    for i in range(end_idx - 1, section_idx, -1):
        if lines[i].strip():
            insert_after = i
            break

    new_lines = lines[:insert_after + 1] + ["", new_entry, ""] + lines[insert_after + 1:]

    result = "\n".join(new_lines)
    # Collapse runs of 4+ blank lines to 2
    result = re.sub(r"\n{4,}", "\n\n\n", result)
    return result


def _insert_timeline_entry(
    content: str,
    draft: str,
    part: str,
    chapter: str,
    scene_id: str,
) -> str:
    """Insert a timeline entry into the appropriate Part / Chapter section.

    Tries to find ``## Part XX`` → ``### Chapter XX`` and inserts at the end
    of that chapter block.  Creates missing Part/Chapter headings as needed.
    Falls back to appending at end of file.
    """
    if not (part and chapter):
        # No structural hint — just append
        return content.rstrip() + f"\n\n{draft}\n"

    part_header = f"## Part {part}"
    chapter_header = f"### Chapter {chapter}"

    lines = content.split("\n")

    # Locate Part heading
    part_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == part_header),
        None,
    )

    if part_idx is None:
        # Part not found — append new Part + Chapter block
        suffix = f"\n{part_header}\n\n{chapter_header}\n\n{draft}\n"
        return content.rstrip() + "\n" + suffix

    # Locate Chapter heading within the Part
    # (stop searching at the next ## heading)
    chapter_idx = None
    part_end = len(lines)
    for i in range(part_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped == chapter_header:
            chapter_idx = i
            break
        if stripped.startswith("## ") and not stripped.startswith("### "):
            part_end = i
            break

    if chapter_idx is None:
        # Chapter not found within this Part — insert new chapter block before part_end
        chapter_block = f"{chapter_header}\n\n{draft}"
        new_lines = lines[:part_end] + ["", chapter_block, ""] + lines[part_end:]
        result = "\n".join(new_lines)
        return re.sub(r"\n{4,}", "\n\n\n", result)

    # Chapter found — insert new entry at the end of the chapter block
    # (just before the next ### or ## heading)
    chap_end = len(lines)
    for i in range(chapter_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            chap_end = i
            break

    insert_after = chapter_idx
    for i in range(chap_end - 1, chapter_idx, -1):
        if lines[i].strip():
            insert_after = i
            break

    new_lines = lines[:insert_after + 1] + ["", draft, ""] + lines[insert_after + 1:]
    result = "\n".join(new_lines)
    return re.sub(r"\n{4,}", "\n\n\n", result)


# ---------------------------------------------------------------------------
# Default stub generators (used when LLM doesn't provide a draft_entry)
# ---------------------------------------------------------------------------

def _default_cast_entry(name: str, scene_id: str) -> str:
    return (
        f"### {name}\n"
        f"- **Age:** [TODO]\n"
        f"- **Role:** [TODO]\n"
        f"- **Physical:** [TODO]\n"
        f"- **Key facts:**\n"
        f"  - First seen: {scene_id}\n"
        f"  - [TODO]\n"
        f"- **Relationships:**\n"
        f"  - [TODO]"
    )


def _default_glossary_entry(term: str, definition: str, scene_id: str) -> str:
    return (
        f"### {term}\n"
        f"**Definition:** {definition}\n"
        f"**First seen:** {scene_id}\n"
        f"**Notes:** [TODO — capitalization, spelling, usage]"
    )


def _default_thread_entry(thread_id: str, scene_id: str) -> str:
    return (
        f"### {thread_id}\n"
        f"**Opened:** {scene_id}\n"
        f"**Question:** [TODO — what question or promise was raised?]\n"
        f"**Status:** Active.\n"
        f"**Notes:** [TODO]"
    )
