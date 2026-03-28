"""Tests for interactive session loop index-audit integration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cli import session_loop


def test_print_help_includes_audit_commands(capsys):
    session_loop._print_help()
    out = capsys.readouterr().out

    assert "audit              - run deterministic index audit" in out
    assert "audit deep         - run deterministic + semantic index audit" in out


@pytest.mark.asyncio
async def test_handle_index_audit_deterministic_uses_loader_and_formatter(
    sample_session_state,
    monkeypatch,
    capsys,
):
    state = sample_session_state
    report = SimpleNamespace(deterministic=[], semantic=[], placeholder_census={})

    load_mock = lambda *_args, **_kwargs: {"CAST.md": ""}
    deterministic_mock = lambda _indexes: report
    semantic_mock = AsyncMock()

    monkeypatch.setattr(session_loop.PlatformFacade, "load_legacy_indexes_from_project", load_mock)
    monkeypatch.setattr(session_loop, "audit_indexes_deterministic", deterministic_mock)
    monkeypatch.setattr(session_loop, "audit_indexes_semantic", semantic_mock)
    monkeypatch.setattr(session_loop, "format_audit_report", lambda _r: "AUDIT REPORT")

    await session_loop._handle_index_audit(state, deep=False)

    assert semantic_mock.await_count == 0
    out = capsys.readouterr().out
    assert "[Running deterministic index audit...]" in out
    assert "AUDIT REPORT" in out


@pytest.mark.asyncio
async def test_handle_index_audit_deep_runs_semantic_with_resolved_model(
    sample_session_state,
    monkeypatch,
    capsys,
):
    state = sample_session_state
    report = SimpleNamespace(deterministic=[], semantic=[], placeholder_census={})

    semantic_result = [
        {
            "check_id": "semantic_contradiction",
            "severity": "warning",
            "file": "THREADS.md",
            "location": "### vault_mystery",
            "message": "Potential contradiction",
            "related_file": "TIMELINE.md",
        }
    ]

    load_mock = lambda *_args, **_kwargs: {"THREADS.md": "", "TIMELINE.md": ""}
    deterministic_mock = lambda _indexes: report
    semantic_mock = AsyncMock(return_value=semantic_result)

    monkeypatch.setattr(session_loop.PlatformFacade, "load_legacy_indexes_from_project", load_mock)
    monkeypatch.setattr(session_loop, "audit_indexes_deterministic", deterministic_mock)
    monkeypatch.setattr(session_loop, "audit_indexes_semantic", semantic_mock)
    monkeypatch.setattr(session_loop, "resolve_model", lambda _name: {"id": "model.deep", "max_tokens": 777})
    monkeypatch.setattr(session_loop, "format_audit_report", lambda _r: "DEEP REPORT")

    await session_loop._handle_index_audit(state, deep=True)

    semantic_mock.assert_awaited_once_with(
        {"THREADS.md": "", "TIMELINE.md": ""},
        state.effective_discussion_client,
        model="model.deep",
        max_tokens=777,
    )
    assert report.semantic == semantic_result
    out = capsys.readouterr().out
    assert "[Running deep index audit...]" in out
    assert "DEEP REPORT" in out


@pytest.mark.asyncio
async def test_handle_index_audit_deep_failure_falls_back_to_deterministic(
    sample_session_state,
    monkeypatch,
    capsys,
):
    state = sample_session_state
    report = SimpleNamespace(deterministic=[], semantic=[], placeholder_census={})

    monkeypatch.setattr(
        session_loop.PlatformFacade,
        "load_legacy_indexes_from_project",
        lambda *_args, **_kwargs: {"CAST.md": ""},
    )
    monkeypatch.setattr(session_loop, "audit_indexes_deterministic", lambda _indexes: report)
    monkeypatch.setattr(session_loop, "audit_indexes_semantic", AsyncMock(side_effect=RuntimeError("provider timeout")))
    monkeypatch.setattr(session_loop, "resolve_model", lambda _name: {"id": "model.deep", "max_tokens": 777})
    monkeypatch.setattr(session_loop, "format_audit_report", lambda _r: "FALLBACK REPORT")

    await session_loop._handle_index_audit(state, deep=True)

    out = capsys.readouterr().out
    assert "Deep audit failed, showing deterministic report only" in out
    assert "provider timeout" in out
    assert "FALLBACK REPORT" in out
