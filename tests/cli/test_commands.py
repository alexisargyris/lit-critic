"""Tests for CLI command helpers."""

from types import SimpleNamespace

import pytest

from cli.commands import _print_session_detail, build_parser, cmd_analyze


def test_print_session_detail_includes_discussion_turn_summary(capsys):
    detail = {
        "id": 12,
        "status": "completed",
        "scene_path": "/tmp/scene.txt",
        "model": "sonnet",
        "created_at": "2026-02-13T12:00:00",
        "findings": [
            {
                "number": 1,
                "severity": "major",
                "lens": "prose",
                "status": "revised",
                "discussion_turns": [
                    {"role": "user", "content": "I meant this rhythm break."},
                    {"role": "assistant", "content": "Got it, downgrading to minor."},
                ],
            }
        ],
    }

    _print_session_detail(detail)
    out = capsys.readouterr().out

    assert "Finding details:" in out
    assert "#1 [major/prose] revised — 2 discussion turn(s)" in out
    assert "Last: Critic: Got it, downgrading to minor." in out


@pytest.mark.asyncio
async def test_cmd_analyze_resolves_auto_lens_preset_to_single_scene(monkeypatch):
    captured_preferences = {}

    def _capture_preferences(payload):
        captured_preferences.update(payload)
        return {"preset": payload["preset"], "weights": {}}

    monkeypatch.setattr("cli.commands.normalize_lens_preferences", _capture_preferences)

    args = SimpleNamespace(
        lens_weight=None,
        lens_preset="auto",
        project="/path/that/does/not/exist",
        scene="/any/scene.txt",
    )

    with pytest.raises(SystemExit):
        await cmd_analyze(args)

    assert captured_preferences["preset"] == "single-scene"


@pytest.mark.asyncio
async def test_cmd_analyze_keeps_manual_lens_preset(monkeypatch):
    captured_preferences = {}

    def _capture_preferences(payload):
        captured_preferences.update(payload)
        return {"preset": payload["preset"], "weights": {}}

    monkeypatch.setattr("cli.commands.normalize_lens_preferences", _capture_preferences)

    args = SimpleNamespace(
        lens_weight=None,
        lens_preset="balanced",
        project="/path/that/does/not/exist",
        scene="/any/scene.txt",
    )

    with pytest.raises(SystemExit):
        await cmd_analyze(args)

    assert captured_preferences["preset"] == "balanced"


def test_build_parser_lens_preset_default_is_auto():
    parser = build_parser()
    args = parser.parse_args(["analyze", "--scene", "s.txt", "--project", "p"])
    assert args.lens_preset == "auto"
