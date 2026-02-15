"""Tests for CLI command helpers."""

from cli.commands import _print_session_detail


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
