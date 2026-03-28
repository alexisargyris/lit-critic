from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from lit_platform.persistence import ExtractionStore, IndexProjectionStore, SceneProjectionStore
from lit_platform.persistence.database import get_connection
from lit_platform.services.project_knowledge_service import (
    compute_input_staleness,
    ensure_project_knowledge_fresh,
    get_project_knowledge_status,
    get_project_knowledge_staleness,
    refresh_project_knowledge,
)


def _configure_scene_discovery(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "user-config.json"
    config_path.write_text(
        json.dumps({"scene_folder": ".", "scene_extensions": ["txt"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIT_CRITIC_USER_CONFIG_PATH", str(config_path))


def _copy_fixture_project(real_novel_dir: Path, tmp_path: Path) -> tuple[list[str], list[str]]:
    scene_files = sorted(path.name for path in real_novel_dir.glob("chapter-*.txt"))[:3]
    index_files = ["CANON.md"]

    for filename in scene_files + index_files:
        shutil.copy2(real_novel_dir / filename, tmp_path / filename)

    return scene_files, index_files


# Sentinel returned by the extraction mock.  It matches the real shape so any
# assertion on result["extraction"] that only checks isinstance(..., dict) passes.
_EXTRACTION_NOOP = {
    "attempted": False,
    "reason": "test_mock",
    "scenes_scanned": 0,
    "extracted": [],
    "skipped_locked": [],
    "failed": [],
}


def _mock_skip_extraction(monkeypatch) -> None:
    """Prevent _refresh_extracted_knowledge from calling asyncio.run() in the
    main thread.  Projection and staleness tests don't exercise extraction
    logic — mocking it out avoids accidental real LLM calls and eliminates
    the Windows ProactorEventLoop hang that occurs after ~640 pytest-asyncio
    function-scoped event loops have accumulated in the same process."""
    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service._refresh_extracted_knowledge",
        lambda *_a, **_kw: _EXTRACTION_NOOP,
    )


def test_refresh_project_knowledge_populates_projections(real_novel_dir: Path, tmp_path: Path, monkeypatch):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, index_files = _copy_fixture_project(real_novel_dir, tmp_path)

    result = refresh_project_knowledge(tmp_path)

    assert result["scene_total"] == len(scene_files)
    assert result["index_total"] == len(index_files)
    assert result["scene_updated"] == len(scene_files)
    assert result["index_updated"] == len(index_files)

    status = get_project_knowledge_status(tmp_path)
    assert status["scenes"]["total"] == len(scene_files)
    assert status["indexes"]["total"] == len(index_files)
    assert status["scenes"]["stale"] == 0
    assert status["indexes"]["stale"] == 0
    assert status["scenes"]["last_refreshed_at"] is not None
    assert status["indexes"]["last_refreshed_at"] is not None


def test_ensure_project_knowledge_fresh_skips_when_not_stale(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    _copy_fixture_project(real_novel_dir, tmp_path)
    refresh_project_knowledge(tmp_path)

    result = ensure_project_knowledge_fresh(tmp_path)

    assert result == {"refreshed": False, "stale_scenes": [], "stale_indexes": []}


def test_get_project_knowledge_staleness_uses_relative_scene_keys(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, _index_files = _copy_fixture_project(real_novel_dir, tmp_path)
    refresh_project_knowledge(tmp_path)

    tracked_scene = scene_files[0]
    conn = get_connection(tmp_path)
    try:
        conn.execute(
            "UPDATE scene_projection SET scene_path = ? WHERE scene_path = ?",
            (str((tmp_path / tracked_scene).resolve()), tracked_scene),
        )
        conn.commit()
    finally:
        conn.close()

    staleness = get_project_knowledge_staleness(tmp_path)
    assert staleness["stale_scenes"] == []
    assert staleness["stale_indexes"] == []


def test_get_project_knowledge_staleness_reports_changed_scene_and_index(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, _index_files = _copy_fixture_project(real_novel_dir, tmp_path)
    refresh_project_knowledge(tmp_path)

    tracked_scene = scene_files[0]
    (tmp_path / tracked_scene).write_text(
        (tmp_path / tracked_scene).read_text(encoding="utf-8") + "\nstaleness change\n",
        encoding="utf-8",
    )
    (tmp_path / "CANON.md").write_text(
        (tmp_path / "CANON.md").read_text(encoding="utf-8") + "\n\n### New Canon Row\ntext\n",
        encoding="utf-8",
    )

    staleness = get_project_knowledge_staleness(tmp_path)
    assert tracked_scene in staleness["stale_scenes"]
    assert "CANON.md" in staleness["stale_indexes"]


def test_refresh_project_knowledge_noop_keeps_response_shape_and_projection_timestamps(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, _index_files = _copy_fixture_project(real_novel_dir, tmp_path)
    refresh_project_knowledge(tmp_path)

    tracked_scene = scene_files[0]
    conn = get_connection(tmp_path)
    try:
        scene_before = SceneProjectionStore.load_by_path(conn, tracked_scene)
        index_before = IndexProjectionStore.load_by_name(conn, "CANON.md")
    finally:
        conn.close()

    assert scene_before is not None
    assert index_before is not None

    result = refresh_project_knowledge(tmp_path)
    assert set(result) == {
        "scenes",
        "indexes",
        "scene_total",
        "scene_updated",
        "index_total",
        "index_updated",
        "chain_warnings",
        "extraction",
    }
    assert result["scenes"] == []
    assert result["indexes"] == []
    assert result["scene_total"] == 0
    assert result["scene_updated"] == 0
    assert result["index_total"] == 0
    assert result["index_updated"] == 0
    assert result["chain_warnings"] == []
    assert isinstance(result["extraction"], dict)

    conn = get_connection(tmp_path)
    try:
        scene_after = SceneProjectionStore.load_by_path(conn, tracked_scene)
        index_after = IndexProjectionStore.load_by_name(conn, "CANON.md")
    finally:
        conn.close()

    assert scene_after is not None
    assert index_after is not None
    assert scene_after["file_hash"] == scene_before["file_hash"]
    assert index_after["file_hash"] == index_before["file_hash"]
    assert scene_after["last_refreshed_at"] == scene_before["last_refreshed_at"]
    assert index_after["last_refreshed_at"] == index_before["last_refreshed_at"]


def test_ensure_project_knowledge_fresh_refreshes_after_scene_and_index_change(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, _index_files = _copy_fixture_project(real_novel_dir, tmp_path)

    refresh_project_knowledge(tmp_path)

    tracked_scene = scene_files[0]
    conn = get_connection(tmp_path)
    try:
        scene_before = SceneProjectionStore.load_by_path(conn, tracked_scene)
        index_before = IndexProjectionStore.load_by_name(conn, "CANON.md")
    finally:
        conn.close()

    assert scene_before is not None
    assert index_before is not None

    (tmp_path / tracked_scene).write_text(
        (tmp_path / tracked_scene).read_text(encoding="utf-8") + "\nNew line for projection refresh.\n",
        encoding="utf-8",
    )
    (tmp_path / "CANON.md").write_text(
        (tmp_path / "CANON.md").read_text(encoding="utf-8") + "\n\n### Added Entry\nDetails\n",
        encoding="utf-8",
    )

    stale_status = get_project_knowledge_status(tmp_path)
    assert stale_status["scenes"]["stale"] >= 1
    assert stale_status["indexes"]["stale"] >= 1

    refreshed = ensure_project_knowledge_fresh(tmp_path)
    assert refreshed["refreshed"] is True
    assert tracked_scene in refreshed["stale_scenes"]
    assert "CANON.md" in refreshed["stale_indexes"]
    assert refreshed["scene_updated"] >= 1
    assert refreshed["index_updated"] >= 1

    conn = get_connection(tmp_path)
    try:
        scene_after = SceneProjectionStore.load_by_path(conn, tracked_scene)
        index_after = IndexProjectionStore.load_by_name(conn, "CANON.md")
    finally:
        conn.close()

    assert scene_after is not None
    assert index_after is not None
    assert scene_after["file_hash"] != scene_before["file_hash"]
    assert index_after["file_hash"] != index_before["file_hash"]


def test_refresh_project_knowledge_recovers_when_passive_db_lacks_projection_tables(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    import sqlite3

    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    scene_files, index_files = _copy_fixture_project(real_novel_dir, tmp_path)

    sqlite3.connect(str(tmp_path / "literary_critic.db")).close()

    result = refresh_project_knowledge(tmp_path)

    assert result["scene_total"] == len(scene_files)
    assert result["index_total"] == len(index_files)
    assert result["scene_updated"] == len(scene_files)
    assert result["index_updated"] == len(index_files)


def test_refresh_project_knowledge_returns_chain_warnings(
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    (tmp_path / "scene-01.txt").write_text(
        "@@META\nNext: scene-02.txt\n@@END\n\nBody 1\n",
        encoding="utf-8",
    )
    (tmp_path / "scene-02.txt").write_text(
        "@@META\nPrev: scene-01.txt\nNext: missing-scene.txt\n@@END\n\nBody 2\n",
        encoding="utf-8",
    )
    (tmp_path / "scene-03.txt").write_text(
        "@@META\nNext: scene-02.txt\n@@END\n\nBody 3\n",
        encoding="utf-8",
    )
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")

    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service._refresh_extracted_knowledge",
        lambda *_args, **_kwargs: {
            "attempted": False,
            "reason": "test",
            "scenes_scanned": 0,
            "extracted": [],
            "skipped_locked": [],
            "failed": [],
        },
    )

    result = refresh_project_knowledge(tmp_path)

    warning_types = {warning["type"] for warning in result["chain_warnings"]}
    assert "gap" in warning_types
    assert "fork" in warning_types


def test_refresh_project_knowledge_extraction_reports_locked_skip(
    tmp_path: Path,
    monkeypatch,
):
    _configure_scene_discovery(monkeypatch, tmp_path)
    (tmp_path / "scene-01.txt").write_text(
        "@@META\nNext: scene-02.txt\n@@END\n\nBody 1\n",
        encoding="utf-8",
    )
    (tmp_path / "scene-02.txt").write_text(
        "@@META\nPrev: scene-01.txt\n@@END\n\nBody 2\n",
        encoding="utf-8",
    )
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")

    conn = get_connection(tmp_path)
    try:
        ExtractionStore.upsert_scene_metadata(
            conn,
            scene_filename="scene-02.txt",
            content_hash="stale",
            extract_status="stale",
            extraction_locked=1,
        )
    finally:
        conn.close()

    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.default_model_slots",
        lambda: {"quick": "fake-quick"},
    )
    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.resolve_model",
        lambda _name: {"provider": "anthropic", "id": "fake-model-id", "max_tokens": 64},
    )
    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.resolve_api_key",
        lambda _provider: "fake-key",
    )

    class _DummyResponse:
        def __init__(self):
            self.text = "{}"
            self.truncated = False

    class _DummyClient:
        async def create_message(self, **_kwargs):
            return _DummyResponse()

    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.create_client",
        lambda _provider, _api_key: _DummyClient(),
    )

    result = refresh_project_knowledge(tmp_path)

    extraction = result["extraction"]
    assert extraction["attempted"] is True
    assert "scene-02.txt" in extraction["skipped_locked"]
    assert "scene-01.txt" in extraction["extracted"]


async def test_refresh_project_knowledge_extraction_inside_event_loop_uses_thread_safe_connection(
    tmp_path: Path,
    monkeypatch,
):
    # This test must be async so that _is_running_in_event_loop() returns True
    # naturally via pytest-asyncio's event loop, rather than via an explicit
    # asyncio.run() call in the test body.  Using asyncio.run() in a sync test
    # causes _run_coro_sync to spawn a thread that itself calls asyncio.run(),
    # and on Windows after hundreds of ProactorEventLoop creations by
    # pytest-asyncio's function-scoped loops the spawned thread hangs waiting
    # for IOCP resources, blocking the thread.join() indefinitely.
    _configure_scene_discovery(monkeypatch, tmp_path)
    (tmp_path / "scene-01.txt").write_text(
        "@@META\n@@END\n\nBody 1\n",
        encoding="utf-8",
    )
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")

    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.default_model_slots",
        lambda: {"quick": "fake-quick"},
    )
    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.resolve_model",
        lambda _name: {"provider": "anthropic", "id": "fake-model-id", "max_tokens": 64},
    )
    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.resolve_api_key",
        lambda _provider: "fake-key",
    )

    class _DummyResponse:
        def __init__(self):
            self.text = "{}"
            self.truncated = False

    class _DummyClient:
        async def create_message(self, **_kwargs):
            return _DummyResponse()

    monkeypatch.setattr(
        "lit_platform.services.project_knowledge_service.create_client",
        lambda _provider, _api_key: _DummyClient(),
    )

    conn = get_connection(tmp_path)
    try:
        # Calling the sync service function from inside an async context means
        # _is_running_in_event_loop() returns True and _run_coro_sync is used.
        # The side-thread it spawns calls asyncio.run() in a clean thread
        # (no accumulated event-loop state), so it completes reliably.
        result = refresh_project_knowledge(tmp_path, conn=conn)
    finally:
        conn.close()

    extraction = result["extraction"]
    assert extraction["attempted"] is True
    assert extraction.get("reason") != "extraction_unavailable"
    assert "SQLite objects created in a thread" not in extraction.get("error", "")


def test_style_staleness_does_not_affect_knowledge(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    """STYLE.md change: affected_knowledge is [] — style changes don't invalidate knowledge."""
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    _copy_fixture_project(real_novel_dir, tmp_path)

    # Create STYLE.md and establish a baseline projection
    style_file = tmp_path / "STYLE.md"
    style_file.write_text("# Style Guide\n\nWrite clearly.", encoding="utf-8")
    refresh_project_knowledge(tmp_path)

    # Inject a fake session so affected_sessions is non-empty
    monkeypatch.setattr(
        "lit_platform.persistence.session_store.SessionStore.list_all",
        staticmethod(lambda conn, **_kw: [{"id": "fake-session-1"}]),
    )

    # Mutate STYLE.md to make it stale
    style_file.write_text("# Style Guide\n\nWrite clearly and concisely.", encoding="utf-8")

    result = compute_input_staleness(tmp_path)
    style_inputs = [i for i in result["stale_inputs"] if "STYLE.md" in i["path"]]
    assert len(style_inputs) == 1
    assert style_inputs[0]["affected_knowledge"] == []
    assert style_inputs[0]["affected_sessions"] == ["fake-session-1"]


def test_canon_staleness_affects_all_knowledge(
    real_novel_dir: Path,
    tmp_path: Path,
    monkeypatch,
):
    """CANON.md change: affected_knowledge is 'all' — world-fact changes invalidate all knowledge."""
    _configure_scene_discovery(monkeypatch, tmp_path)
    _mock_skip_extraction(monkeypatch)
    _copy_fixture_project(real_novel_dir, tmp_path)
    refresh_project_knowledge(tmp_path)

    # Mutate CANON.md to make it stale
    (tmp_path / "CANON.md").write_text(
        (tmp_path / "CANON.md").read_text(encoding="utf-8") + "\n\n### New Canon Entry\nDetails\n",
        encoding="utf-8",
    )

    result = compute_input_staleness(tmp_path)
    canon_inputs = [i for i in result["stale_inputs"] if "CANON.md" in i["path"]]
    assert len(canon_inputs) == 1
    assert canon_inputs[0]["affected_knowledge"] == "all"


def test_canon_forces_reextraction_of_previously_extracted_scenes(
    tmp_path: Path,
    monkeypatch,
):
    """CANON.md change: _refresh_extracted_knowledge marks previously-extracted scenes stale."""
    from lit_platform.services.project_knowledge_service import _refresh_extracted_knowledge

    _configure_scene_discovery(monkeypatch, tmp_path)
    (tmp_path / "scene-01.txt").write_text("@@META\n@@END\n\nBody\n", encoding="utf-8")
    (tmp_path / "CANON.md").write_text("canon", encoding="utf-8")

    conn = get_connection(tmp_path)
    try:
        # Pre-seed scene as already extracted AND locked so the extraction pass skips it.
        # This lets us confirm the canon_stale mark-stale step ran by checking the DB state.
        ExtractionStore.upsert_scene_metadata(
            conn,
            scene_filename="scene-01.txt",
            content_hash="abc123",
            extract_status="extracted",
            extraction_locked=1,
        )

        monkeypatch.setattr(
            "lit_platform.services.project_knowledge_service.default_model_slots",
            lambda: {"quick": "fake-quick"},
        )
        monkeypatch.setattr(
            "lit_platform.services.project_knowledge_service.resolve_model",
            lambda _name: {"provider": "anthropic", "id": "fake-model-id", "max_tokens": 64},
        )
        monkeypatch.setattr(
            "lit_platform.services.project_knowledge_service.resolve_api_key",
            lambda _provider: "fake-key",
        )

        class _DummyResponse:
            def __init__(self):
                self.text = "{}"
                self.truncated = False

        class _DummyClient:
            async def create_message(self, **_kwargs):
                return _DummyResponse()

        monkeypatch.setattr(
            "lit_platform.services.project_knowledge_service.create_client",
            lambda _provider, _api_key: _DummyClient(),
        )

        _refresh_extracted_knowledge(tmp_path, conn, should_attempt=True, canon_stale=True)

        # The scene must be stale: canon_stale triggered mark_scene_stale and the lock
        # caused extraction to skip it, so the status stays 'stale'.
        row = conn.execute(
            "SELECT extract_status FROM extracted_scene_metadata WHERE scene_filename = ?",
            ("scene-01.txt",),
        ).fetchone()
        assert row is not None
        assert row["extract_status"] == "stale"
    finally:
        conn.close()
