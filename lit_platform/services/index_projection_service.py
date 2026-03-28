"""Index projection refresh and query utilities."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lit_platform.persistence import IndexProjectionStore
from lit_platform.persistence.database import get_connection, get_passive_connection
from lit_platform.services.audit_service import _split_h3_entries
from lit_platform.services.scene_projection_service import compute_file_hash

_INDEX_FILENAMES = (
    "CANON.md",
    "CAST.md",
    "GLOSSARY.md",
    "STYLE.md",
    "THREADS.md",
    "TIMELINE.md",
)

_INDEX_SCOPE_BY_NAME = {
    "CANON.md": "canon",
    "CAST.md": "cast",
    "GLOSSARY.md": "glossary",
    "STYLE.md": "style",
    "THREADS.md": "threads",
    "TIMELINE.md": "timeline",
}


def parse_index_entries(index_name: str, content: str) -> list[dict] | None:
    """Parse structured index entries from a markdown index file content."""
    normalized_name = Path(index_name).name.upper()
    if normalized_name == "STYLE.MD":
        return None
    if not content.strip():
        return []

    lines = content.splitlines()
    section_by_line = _sections_by_line(lines)
    scope = _INDEX_SCOPE_BY_NAME.get(normalized_name, Path(index_name).stem.lower())

    entries: list[dict] = []
    for heading, line_no, _entry_text in _split_h3_entries(content):
        entry = heading.split("<!--", 1)[0].strip()
        if not entry:
            continue
        entries.append(
            {
                "scope": scope,
                "entry": entry,
                "source_file": Path(index_name).name,
                "source_section": section_by_line.get(line_no, ""),
                "source_line": line_no,
            }
        )
    return entries


def refresh_index_projection(
    project_path: Path,
    index_name: str | Path,
    conn: sqlite3.Connection,
) -> dict:
    """Refresh one index projection if the source hash changed."""
    project_root = Path(project_path)
    candidate = Path(index_name)

    if candidate.is_absolute():
        index_file = candidate
        stored_name = candidate.name
    else:
        index_file = project_root / candidate
        stored_name = candidate.as_posix()

    if not index_file.exists():
        return {"index_name": stored_name, "updated": False, "missing": True}

    raw_content_hash = compute_file_hash(index_file)
    if not IndexProjectionStore.is_stale(conn, stored_name, raw_content_hash):
        return {
            "index_name": stored_name,
            "updated": False,
            "file_hash": raw_content_hash,
        }

    content = index_file.read_text(encoding="utf-8")
    entries = parse_index_entries(stored_name, content)
    IndexProjectionStore.upsert(
        conn,
        index_name=stored_name,
        file_hash=raw_content_hash,
        entries_json=entries,
        raw_content_hash=raw_content_hash,
    )
    return {
        "index_name": stored_name,
        "updated": True,
        "file_hash": raw_content_hash,
    }


def refresh_all_indexes(project_path: Path, conn: sqlite3.Connection) -> list[dict]:
    """Refresh all discovered canonical index files for a project."""
    project_root = Path(project_path)
    refresh_results: list[dict] = []

    for index_name in _INDEX_FILENAMES:
        index_file = project_root / index_name
        if not index_file.exists():
            continue
        refresh_results.append(refresh_index_projection(project_root, index_name, conn))
    return refresh_results


def list_index_projections(project_path: Path) -> list[dict]:
    """Return all stored index projections for a project."""
    conn = get_passive_connection(Path(project_path))
    if conn is None:
        return []
    try:
        return IndexProjectionStore.load_all(conn)
    finally:
        conn.close()


def get_stale_indexes(project_path: Path) -> list[str]:
    """Return index names that are missing, new, or hash-mismatched."""
    project_root = Path(project_path)
    conn = get_connection(project_root)
    try:
        stored = {row["index_name"] for row in IndexProjectionStore.load_all(conn)}
        existing = {
            index_name
            for index_name in _INDEX_FILENAMES
            if (project_root / index_name).exists()
        }
        candidates = sorted(stored | existing)

        stale: list[str] = []
        for index_name in candidates:
            index_file = project_root / index_name
            if not index_file.exists():
                stale.append(index_name)
                continue
            current_hash = compute_file_hash(index_file)
            if IndexProjectionStore.is_stale(conn, index_name, current_hash):
                stale.append(index_name)
        return stale
    finally:
        conn.close()


def _sections_by_line(lines: list[str]) -> dict[int, str]:
    """Map heading line numbers to nearest preceding section title."""
    section_starts: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            section_starts.append((line_no, stripped[3:].strip()))

    line_to_section: dict[int, str] = {}
    current_section = ""
    section_idx = 0
    for line_no, line in enumerate(lines, start=1):
        while section_idx < len(section_starts) and section_starts[section_idx][0] <= line_no:
            current_section = section_starts[section_idx][1]
            section_idx += 1
        if line.strip().startswith("### "):
            line_to_section[line_no] = current_section
    return line_to_section


__all__ = [
    "get_stale_indexes",
    "list_index_projections",
    "parse_index_entries",
    "refresh_all_indexes",
    "refresh_index_projection",
]