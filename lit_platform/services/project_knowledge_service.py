"""Project-knowledge projection orchestration helpers."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path

from lit_platform.persistence import IndexProjectionStore, SceneProjectionStore
from lit_platform.persistence.database import get_connection, get_passive_connection
from lit_platform.runtime.config import MAX_TOKENS, resolve_api_key, resolve_model
from lit_platform.runtime.llm import create_client
import logging

from lit_platform.runtime.model_slots import SLOT_QUICK, default_model_slots

logger = logging.getLogger(__name__)

from lit_platform.persistence.extraction_store import ExtractionStore
from lit_platform.persistence.knowledge_state_store import KnowledgeStateStore
from lit_platform.runtime.prompts import get_knowledge_reconciliation_prompt
from lit_platform.services.extraction_service import (
    cleanup_orphaned_entities,
    extract_stale_scenes,
    reconcile_knowledge,
)
from lit_platform.user_config import get_knowledge_review_pass_setting
from lit_platform.services.index_projection_service import refresh_index_projection
from lit_platform.services.scene_projection_service import (
    compute_file_hash,
    discover_scene_relative_paths,
    refresh_all_scenes,
)

_INDEX_FILENAMES = (
    "CANON.md",
    "STYLE.md",
)


def refresh_project_knowledge(
    project_path: Path,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Refresh scene projections, chain validation, extraction, and canon/style projections."""
    project_root = Path(project_path)
    stale_scenes, stale_indexes = _detect_stale_project_knowledge(project_root)
    if not stale_scenes and not stale_indexes:
        return {
            "scenes": [],
            "indexes": [],
            "scene_total": 0,
            "scene_updated": 0,
            "index_total": 0,
            "index_updated": 0,
            "chain_warnings": [],
            "extraction": _empty_extraction_result(reason="no_stale_scenes"),
        }

    owns_connection = conn is None
    active_conn = conn or get_connection(project_root)

    # Re-extraction resolves staleness — clear the persisted cache so the
    # tree view doesn't show stale indicators from a previous "Check" run.
    KnowledgeStateStore.clear_staleness_cache(active_conn)

    try:
        scene_results = refresh_all_scenes(project_root, active_conn)
        index_results = _refresh_canon_style_indexes(project_root, active_conn)
        chain_warnings = _validate_prev_next_chain(
            project_root,
            SceneProjectionStore.load_all(active_conn, project_path=project_root),
        )
        extraction = _refresh_extracted_knowledge(
            project_root,
            active_conn,
            should_attempt=bool(stale_scenes) or "CANON.md" in stale_indexes,
            canon_stale="CANON.md" in stale_indexes,
        )
        return {
            "scenes": scene_results,
            "indexes": index_results,
            "scene_total": len(scene_results),
            "scene_updated": sum(1 for row in scene_results if row.get("updated")),
            "index_total": len(index_results),
            "index_updated": sum(1 for row in index_results if row.get("updated")),
            "chain_warnings": chain_warnings,
            "extraction": extraction,
        }
    finally:
        if owns_connection:
            active_conn.close()


def get_project_knowledge_staleness(project_path: Path) -> dict[str, list[str]]:
    """Return stale scene/index keys using passive DB reads when possible."""
    project_root = Path(project_path)
    stale_scenes, stale_indexes = _detect_stale_project_knowledge(project_root)
    return {
        "stale_scenes": stale_scenes,
        "stale_indexes": stale_indexes,
    }


def get_project_knowledge_status(project_path: Path) -> dict:
    """Return stale/fresh counts and latest refresh timestamps for projections."""
    project_root = Path(project_path)
    conn = get_passive_connection(project_root)
    if conn is None:
        # DB does not exist yet — return zeroes rather than triggering DB creation.
        return {
            "scenes": {"total": 0, "stale": 0, "fresh": 0, "last_refreshed_at": None},
            "indexes": {"total": 0, "stale": 0, "fresh": 0, "last_refreshed_at": None},
            "stale_total": 0,
            "fresh_total": 0,
        }
    try:
        stale_scenes = _get_stale_scenes(project_root, conn)
        stale_indexes = _get_stale_indexes(project_root, conn)

        scene_rows = SceneProjectionStore.load_all(conn, project_path=project_root)
        index_rows = IndexProjectionStore.load_all(conn)

        scene_total = len(
            {
                _normalize_scene_key(project_root, row["scene_path"])
                for row in scene_rows
            }
            | set(_discover_scene_relative_paths(project_root))
        )
        index_total = len(
            {Path(row["index_name"]).name for row in index_rows}
            | _existing_index_names(project_root)
        )

        scene_last_refreshed = max(
            (row.get("last_refreshed_at") for row in scene_rows if row.get("last_refreshed_at")),
            default=None,
        )
        index_last_refreshed = max(
            (row.get("last_refreshed_at") for row in index_rows if row.get("last_refreshed_at")),
            default=None,
        )

        scene_fresh = max(scene_total - len(stale_scenes), 0)
        index_fresh = max(index_total - len(stale_indexes), 0)

        return {
            "scenes": {
                "total": scene_total,
                "stale": len(stale_scenes),
                "fresh": scene_fresh,
                "last_refreshed_at": scene_last_refreshed,
            },
            "indexes": {
                "total": index_total,
                "stale": len(stale_indexes),
                "fresh": index_fresh,
                "last_refreshed_at": index_last_refreshed,
            },
            "stale_total": len(stale_scenes) + len(stale_indexes),
            "fresh_total": scene_fresh + index_fresh,
        }
    except sqlite3.OperationalError:
        return {
            "scenes": {"total": 0, "stale": 0, "fresh": 0, "last_refreshed_at": None},
            "indexes": {"total": 0, "stale": 0, "fresh": 0, "last_refreshed_at": None},
            "stale_total": 0,
            "fresh_total": 0,
        }
    finally:
        conn.close()


def ensure_project_knowledge_fresh(
    project_path: Path,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Refresh projections only if any scene/index source appears stale."""
    project_root = Path(project_path)

    stale_scenes, stale_indexes = _detect_stale_project_knowledge(project_root)
    if not stale_scenes and not stale_indexes:
        return {
            "refreshed": False,
            "stale_scenes": [],
            "stale_indexes": [],
        }

    refreshed = refresh_project_knowledge(project_root, conn=conn)
    refreshed["refreshed"] = True
    refreshed["stale_scenes"] = stale_scenes
    refreshed["stale_indexes"] = stale_indexes
    return refreshed


def compute_input_staleness(project_path: Path) -> dict:
    """Return which input files are stale and the knowledge/sessions they affect.

    Checks CANON.md, STYLE.md (references) and all scene files. For each stale
    input returns the type, path, affected knowledge entries, and affected session ids.

    Returns::

        {
            "stale_inputs": [
                {
                    "path": "<absolute path>",
                    "type": "reference" | "scene",
                    "affected_knowledge": [{"category": ..., "entity_key": ...}] | "all",
                    "affected_sessions": [<session id>, ...],
                }
            ]
        }
    """
    project_root = Path(project_path)
    conn = get_passive_connection(project_root)
    if conn is None:
        return {"stale_inputs": []}
    try:
        result = _compute_staleness(project_root, conn)
    finally:
        conn.close()

    # Persist computed staleness so it survives restarts and DB copies.
    _persist_staleness_cache(project_root, result["stale_inputs"])
    return result


def _discover_scene_relative_paths(project_root: Path) -> list[str]:
    """Discover scene files using configured folder/extensions."""
    return discover_scene_relative_paths(project_root)


def _get_stale_scenes(project_root: Path, conn: sqlite3.Connection) -> list[str]:
    """Return scene projection keys that are missing, new, or hash-mismatched."""
    stored_hashes = _scene_hashes_by_normalized_key(project_root, conn)
    stored = set(stored_hashes)
    existing = set(_discover_scene_relative_paths(project_root))
    candidates = sorted(stored | existing)

    stale: list[str] = []
    for scene_key in candidates:
        scene_path = Path(scene_key)
        scene_file = scene_path if scene_path.is_absolute() else project_root / scene_path
        if not scene_file.exists():
            stale.append(scene_key)
            continue
        current_hash = compute_file_hash(scene_file)
        stored_hash = stored_hashes.get(scene_key)
        if stored_hash != current_hash:
            stale.append(scene_key)
    return stale


def _scene_hashes_by_normalized_key(
    project_root: Path,
    conn: sqlite3.Connection,
) -> dict[str, str]:
    """Load stored scene hashes indexed by normalized scene keys."""
    normalized_hashes: dict[str, str] = {}
    for row in SceneProjectionStore.load_all(conn, project_path=project_root):
        normalized_hashes[_normalize_scene_key(project_root, row["scene_path"])] = row[
            "file_hash"
        ]
    return normalized_hashes


def _normalize_scene_key(project_root: Path, scene_key: str) -> str:
    """Normalize scene keys to project-root-relative POSIX paths when possible."""
    candidate = Path(scene_key)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(project_root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _existing_index_names(project_root: Path) -> set[str]:
    """Return canonical index filenames that currently exist on disk."""
    return {name for name in _INDEX_FILENAMES if (project_root / name).exists()}


def _refresh_canon_style_indexes(
    project_root: Path,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Refresh only authored canon/style index projections."""
    results: list[dict] = []
    for index_name in _INDEX_FILENAMES:
        index_file = project_root / index_name
        if not index_file.exists():
            continue
        results.append(refresh_index_projection(project_root, index_name, conn))
    return results


def _refresh_extracted_knowledge(
    project_root: Path,
    conn: sqlite3.Connection,
    *,
    should_attempt: bool,
    canon_stale: bool = False,
) -> dict:
    """Run stale-scene extraction using the hardcoded quick model slot.

    When *canon_stale* is True all previously-extracted scenes are force-marked
    stale before extraction begins, because a CANON.md change may invalidate any
    previously extracted knowledge regardless of scene content hashes.
    """
    if not should_attempt:
        return _empty_extraction_result(reason="no_stale_scenes")

    if canon_stale:
        # Force re-extraction of every known scene so the upcoming pass
        # re-evaluates them against the updated canon.
        for meta_row in ExtractionStore.load_all_scene_metadata(conn):
            ExtractionStore.mark_scene_stale(conn, meta_row["scene_filename"])

    try:
        extraction_model = default_model_slots()[SLOT_QUICK]
        model_cfg = resolve_model(extraction_model)
        provider = str(model_cfg["provider"])
        model_id = str(model_cfg["id"])
        max_tokens = int(model_cfg.get("max_tokens") or MAX_TOKENS)
        api_key = resolve_api_key(provider)
        client = create_client(provider, api_key)

        if _is_running_in_event_loop():
            result = _run_coro_sync(
                _extract_stale_scenes_with_fresh_connection(
                    project_root=project_root,
                    client=client,
                    model=model_id,
                    max_tokens=max_tokens,
                )
            )
        else:
            result = _run_coro_sync(
                extract_stale_scenes(
                    project_path=project_root,
                    conn=conn,
                    client=client,
                    model=model_id,
                    max_tokens=max_tokens,
                )
            )
        result["attempted"] = True
        result["reason"] = "partial_failure" if result.get("failed") else "ok"
        result["model_slot"] = SLOT_QUICK
        result["model_name"] = extraction_model

        # Reconciliation review pass
        result["flagged_for_review"] = _run_reconciliation_pass(
            project_root=project_root,
            client=client,
            model_id=model_id,
            max_tokens=max_tokens,
            extraction_result=result,
        )

        # Persist flags so they survive restarts and DB copies
        KnowledgeStateStore.save_review_flags(conn, result["flagged_for_review"])

        return result
    except Exception as exc:  # noqa: BLE001 - refresh should remain non-fatal
        return _empty_extraction_result(
            reason="extraction_unavailable",
            error=str(exc),
        )


def _compute_staleness(project_root: Path, conn: sqlite3.Connection) -> dict:
    """Core staleness logic — runs against a passive DB connection."""
    import hashlib
    from lit_platform.persistence.session_store import SessionStore

    stale_inputs: list[dict] = []
    stored_index_hashes = _index_hashes_by_canonical_name(conn)
    all_sessions = SessionStore.list_all(conn, project_path=project_root)

    # --- References: CANON.md and STYLE.md ---
    for ref_name in _INDEX_FILENAMES:
        ref_file = project_root / ref_name
        if not ref_file.exists():
            continue
        current_hash = compute_file_hash(ref_file)
        if stored_index_hashes.get(ref_name) == current_hash:
            continue
        # Reference changed — all sessions are affected (combined hash cannot
        # distinguish which reference a session used, so we flag all sessions).
        # STYLE.md governs prose/style only — knowledge entries are not affected.
        # CANON.md governs world facts — all knowledge entries may be invalidated.
        affected_knowledge: list | str = [] if ref_name == "STYLE.md" else "all"
        stale_inputs.append({
            "path": str(ref_file),
            "type": "reference",
            "affected_knowledge": affected_knowledge,
            "affected_sessions": [s["id"] for s in all_sessions],
        })

    # --- Scene files ---
    stored_scene_hashes = _scene_hashes_by_normalized_key(project_root, conn)
    all_scene_keys = sorted(
        set(stored_scene_hashes) | set(_discover_scene_relative_paths(project_root))
    )
    for scene_key in all_scene_keys:
        scene_path = Path(scene_key)
        scene_file = scene_path if scene_path.is_absolute() else project_root / scene_path
        if not scene_file.exists():
            continue
        current_file_hash = compute_file_hash(scene_file)
        if stored_scene_hashes.get(scene_key) == current_file_hash:
            continue

        # Compute the scene_hash used by sessions (SHA256 of text content, 16 chars).
        scene_content = scene_file.read_text(encoding="utf-8")
        current_scene_hash = hashlib.sha256(scene_content.encode("utf-8")).hexdigest()[:16]

        scene_filename = Path(scene_key).name
        affected_knowledge = _knowledge_affected_by_scene(conn, scene_filename)

        # Sessions that include this scene and whose scene_hash mismatches.
        affected_session_ids = []
        for s in all_sessions:
            scene_paths = s.get("scene_paths") or []
            if scene_filename not in {Path(p).name for p in scene_paths}:
                continue
            if s.get("scene_hash", "") != current_scene_hash:
                affected_session_ids.append(s["id"])

        stale_inputs.append({
            "path": str(scene_file),
            "type": "scene",
            "affected_knowledge": affected_knowledge,
            "affected_sessions": affected_session_ids,
        })

    return {"stale_inputs": stale_inputs}


def _knowledge_affected_by_scene(
    conn: sqlite3.Connection,
    scene_filename: str,
) -> list[dict]:
    """Return knowledge entries sourced from *scene_filename*."""
    affected: list[dict] = []

    rows = conn.execute(
        "SELECT name FROM extracted_character_sources WHERE scene_filename = ? ORDER BY name",
        (scene_filename,),
    ).fetchall()
    for row in rows:
        affected.append({"category": "characters", "entity_key": row["name"]})

    rows = conn.execute(
        "SELECT term FROM extracted_term_sources WHERE scene_filename = ? ORDER BY term",
        (scene_filename,),
    ).fetchall()
    for row in rows:
        affected.append({"category": "terms", "entity_key": row["term"]})

    rows = conn.execute(
        "SELECT thread_id FROM extracted_thread_events WHERE scene_filename = ? ORDER BY thread_id",
        (scene_filename,),
    ).fetchall()
    for row in rows:
        affected.append({"category": "threads", "entity_key": row["thread_id"]})

    row = conn.execute(
        "SELECT scene_filename FROM extracted_timeline WHERE scene_filename = ?",
        (scene_filename,),
    ).fetchone()
    if row:
        affected.append({"category": "timeline", "entity_key": scene_filename})

    return affected


def _empty_extraction_result(reason: str, error: str | None = None) -> dict:
    """Build a consistent extraction result payload for skipped/failed attempts."""
    payload: dict = {
        "attempted": False,
        "reason": reason,
        "scenes_scanned": 0,
        "extracted": [],
        "skipped_locked": [],
        "failed": [],
    }
    if error:
        payload["error"] = error
    return payload


async def _extract_stale_scenes_with_fresh_connection(
    *,
    project_root: Path,
    client,
    model: str,
    max_tokens: int,
) -> dict:
    """Run extraction with a connection opened on the executing thread."""
    extraction_conn = get_connection(project_root)
    try:
        return await extract_stale_scenes(
            project_path=project_root,
            conn=extraction_conn,
            client=client,
            model=model,
            max_tokens=max_tokens,
        )
    finally:
        extraction_conn.close()


def _is_running_in_event_loop() -> bool:
    """Return ``True`` when called from within an active asyncio event loop."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _run_coro_sync(coro):
    """Run a coroutine from sync code, including when already inside an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, dict] = {}
    error_box: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            error_box["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error_box:
        raise error_box["value"]
    return result_box.get("value", {})


def _validate_prev_next_chain(project_root: Path, scene_rows: list[dict]) -> list[dict]:
    """Validate Prev/Next graph and return non-fatal chain warnings."""
    if not scene_rows:
        return []

    normalized_rows = {
        _normalize_scene_key(project_root, str(row.get("scene_path") or "")): row
        for row in scene_rows
    }
    scene_paths = sorted(path for path in normalized_rows if path)
    scene_set = set(scene_paths)
    if not scene_paths:
        return []

    prev_refs: dict[str, str | None] = {}
    next_refs: dict[str, str | None] = {}
    incoming: dict[str, int] = {}
    next_claims: dict[str, list[str]] = {}
    warnings: list[dict] = []

    for scene_path in scene_paths:
        meta = _coerce_meta_json(normalized_rows[scene_path].get("meta_json"))
        prev_ref = _normalize_chain_ref(meta.get("prev"))
        next_ref = _normalize_chain_ref(meta.get("next"))
        prev_refs[scene_path] = prev_ref
        next_refs[scene_path] = next_ref

        if prev_ref and prev_ref not in scene_set:
            warnings.append(
                {
                    "type": "gap",
                    "scene": scene_path,
                    "field": "prev",
                    "target": prev_ref,
                }
            )
        if next_ref and next_ref not in scene_set:
            warnings.append(
                {
                    "type": "gap",
                    "scene": scene_path,
                    "field": "next",
                    "target": next_ref,
                }
            )

        if next_ref and next_ref in scene_set:
            incoming[next_ref] = incoming.get(next_ref, 0) + 1
            next_claims.setdefault(next_ref, []).append(scene_path)

    for target, sources in sorted(next_claims.items()):
        if len(sources) > 1:
            warnings.append(
                {
                    "type": "fork",
                    "target": target,
                    "sources": sorted(sources),
                }
            )

    visited: set[str] = set()
    seen_cycles: set[tuple[str, ...]] = set()
    for start in scene_paths:
        if start in visited:
            continue
        order: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start

        while current and current in scene_set and current not in visited:
            if current in positions:
                cycle = tuple(order[positions[current] :])
                if cycle and cycle not in seen_cycles:
                    warnings.append({"type": "cycle", "scenes": list(cycle)})
                    seen_cycles.add(cycle)
                break
            positions[current] = len(order)
            order.append(current)
            next_ref = next_refs.get(current)
            if not next_ref or next_ref not in scene_set:
                break
            current = next_ref

        visited.update(order)

    if len(scene_paths) > 1:
        for scene_path in scene_paths:
            has_incoming = incoming.get(scene_path, 0) > 0
            next_ref = next_refs.get(scene_path)
            has_outgoing = bool(next_ref and next_ref in scene_set)
            if not has_incoming and not has_outgoing:
                warnings.append({"type": "orphan", "scene": scene_path})

    return warnings


def _coerce_meta_json(raw_meta: object) -> dict[str, str]:
    """Normalize stored projection metadata to a dict for chain validation."""
    if isinstance(raw_meta, dict):
        return raw_meta
    if isinstance(raw_meta, str):
        try:
            parsed = json.loads(raw_meta)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_chain_ref(value: object) -> str | None:
    """Normalize a Prev/Next reference value to a canonical scene key."""
    if value is None:
        return None
    ref = str(value).strip()
    if not ref:
        return None
    if ref.lower() in {"none", "null", "tbd", "n/a", "na"}:
        return None
    return Path(ref).as_posix()


def _get_stale_indexes(project_root: Path, conn: sqlite3.Connection) -> list[str]:
    """Return index projection keys that are missing, new, or hash-mismatched."""
    stored_hashes = _index_hashes_by_canonical_name(conn)
    stored = set(stored_hashes)
    existing = _existing_index_names(project_root)
    candidates = sorted(stored | existing)

    stale: list[str] = []
    for index_name in candidates:
        index_file = project_root / index_name
        if not index_file.exists():
            stale.append(index_name)
            continue
        current_hash = compute_file_hash(index_file)
        stored_hash = stored_hashes.get(index_name)
        if stored_hash != current_hash:
            stale.append(index_name)
    return stale


def _index_hashes_by_canonical_name(conn: sqlite3.Connection) -> dict[str, str]:
    """Load stored index hashes by canonical index file name."""
    normalized_hashes: dict[str, str] = {}
    for row in IndexProjectionStore.load_all(conn):
        normalized_hashes[Path(row["index_name"]).name] = row["file_hash"]
    return normalized_hashes


def _detect_stale_project_knowledge(project_root: Path) -> tuple[list[str], list[str]]:
    """Detect stale scene/index keys without opening write-capable DB connections."""
    conn = get_passive_connection(project_root)
    if conn is None:
        return sorted(_discover_scene_relative_paths(project_root)), sorted(
            _existing_index_names(project_root)
        )

    try:
        return _get_stale_scenes(project_root, conn), _get_stale_indexes(project_root, conn)
    except sqlite3.OperationalError:
        return sorted(_discover_scene_relative_paths(project_root)), sorted(
            _existing_index_names(project_root)
        )
    finally:
        conn.close()


def _run_reconciliation_pass(
    *,
    project_root: Path,
    client,
    model_id: str,
    max_tokens: int,
    extraction_result: dict,
) -> list[dict]:
    """Run the knowledge reconciliation review pass after extraction.

    Returns a (possibly empty) list of flagged-for-review items.
    Skips gracefully on any error so it never breaks the refresh flow.
    """
    trigger = get_knowledge_review_pass_setting()
    if trigger == "never":
        return []
    if trigger == "on_stale" and not extraction_result.get("extracted"):
        return []

    try:
        conn = get_connection(project_root)
        try:
            # --- Step 1: deterministic orphan cleanup (no LLM needed) ---
            # After extraction, any character/term with zero remaining source rows
            # is definitively absent from all scene text. Remove them immediately.
            orphan_result = cleanup_orphaned_entities(conn)
            logger.info(
                "Orphan cleanup: %d removed, %d flagged for review",
                len(orphan_result.get("removed", [])),
                len(orphan_result.get("flagged_for_review", [])),
            )
            all_flagged = list(orphan_result.get("flagged_for_review", []))

            # --- Step 2: LLM reconciliation for field updates and subtler removals ---
            knowledge_json = _build_knowledge_json_for_reconciliation(conn)
            scene_summaries_text = _build_scene_summaries_text_for_reconciliation(conn)
            prompt = get_knowledge_reconciliation_prompt(knowledge_json, scene_summaries_text)
            llm_output = _run_coro_sync(
                _call_llm_for_reconciliation(client, model_id, max_tokens, prompt)
            )
            rec_result = reconcile_knowledge(conn, llm_output)
            logger.info(
                "LLM reconciliation pass: %d updates, %d removals, %d flagged",
                rec_result.get("applied_updates", 0),
                rec_result.get("applied_removals", 0),
                len(rec_result.get("flagged_for_review", [])),
            )
            # Merge LLM-flagged items, deduplicating by (category, entity_key)
            seen_keys = {
                (item["category"], item["entity_key"]) for item in all_flagged
            }
            for item in rec_result.get("flagged_for_review", []):
                key = (item["category"], item["entity_key"])
                if key not in seen_keys:
                    all_flagged.append(item)
                    seen_keys.add(key)

            return all_flagged
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - reconciliation is non-fatal
        logger.warning("Reconciliation pass failed (non-fatal): %s", exc)
        return []


def _build_knowledge_json_for_reconciliation(conn: sqlite3.Connection) -> str:
    """Serialize extracted knowledge as JSON including entity lock status."""
    snapshot = {
        "characters": ExtractionStore.load_all_characters(conn),
        "terms": ExtractionStore.load_all_terms(conn),
        "threads": ExtractionStore.load_all_threads(conn),
        "timeline": ExtractionStore.load_all_timeline(conn),
    }
    return json.dumps(snapshot, ensure_ascii=False)


def _build_scene_summaries_text_for_reconciliation(conn: sqlite3.Connection) -> str:
    """Build a plain-text scene summary block for the reconciliation prompt.

    Each line includes the scene filename, location, objective, and the
    ``cast_present`` list so the reconciliation LLM can detect when a
    character no longer appears in any scene (e.g. after a rename).
    """
    rows = ExtractionStore.load_all_scene_metadata(conn)
    if not rows:
        return "[No scene summaries available]"
    lines: list[str] = []
    for row in rows:
        parts = [f"Scene: {row['scene_filename']}"]
        if row.get("location"):
            parts.append(f"Location: {row['location']}")
        if row.get("objective"):
            parts.append(f"Objective: {row['objective']}")
        raw_cast = row.get("cast_present")
        if raw_cast:
            # cast_present is stored as a JSON list string; parse it gracefully.
            if isinstance(raw_cast, list):
                cast_names = raw_cast
            else:
                try:
                    cast_names = json.loads(raw_cast)
                except (TypeError, ValueError):
                    cast_names = []
            if cast_names:
                parts.append(f"Cast: {', '.join(str(n) for n in cast_names)}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _persist_staleness_cache(project_root: Path, stale_inputs: list[dict]) -> None:
    """Write staleness cache to DB after a compute pass.

    Opens a brief write connection.  Errors are non-fatal — the caller has
    already returned the staleness result to the client.
    """
    try:
        write_conn = get_connection(project_root)
        try:
            # If any stale input marks all knowledge as stale, use the sentinel.
            all_stale = any(
                item.get("affected_knowledge") == "all" for item in stale_inputs
            )
            if all_stale or not stale_inputs:
                KnowledgeStateStore.save_staleness_cache(
                    write_conn, [], all_stale=all_stale
                )
            else:
                seen: set[tuple[str, str]] = set()
                entities: list[dict] = []
                for item in stale_inputs:
                    for entry in item.get("affected_knowledge") or []:
                        key = (entry["category"], entry["entity_key"])
                        if key not in seen:
                            entities.append(entry)
                            seen.add(key)
                KnowledgeStateStore.save_staleness_cache(
                    write_conn, entities, all_stale=False
                )
        finally:
            write_conn.close()
    except Exception as exc:  # noqa: BLE001 - staleness persist is non-fatal
        logger.warning("Failed to persist staleness cache (non-fatal): %s", exc)


async def _call_llm_for_reconciliation(
    client, model_id: str, max_tokens: int, prompt: str
) -> str:
    """Call the LLM for the reconciliation prompt and return raw text."""
    response = await client.create_message(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.text


__all__ = [
    "ensure_project_knowledge_fresh",
    "get_project_knowledge_staleness",
    "get_project_knowledge_status",
    "refresh_project_knowledge",
]
