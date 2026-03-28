"""Tests for CLI command helpers."""

from types import SimpleNamespace

import pytest

from cli.commands import _normalize_focus_area_aliases, _print_session_detail, build_parser, cmd_analyze, cmd_knowledge


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


def test_build_parser_mode_default_is_deep():
    parser = build_parser()
    args = parser.parse_args(["sessions", "start", "--scene", "s.txt", "--project", "p"])
    assert args.mode == "deep"


def test_build_parser_supports_sessions_start_command():
    parser = build_parser()
    args = parser.parse_args(["sessions", "start", "--scene", "s.txt", "--project", "p"])

    assert args.command == "sessions"
    assert args.sessions_action == "start"
    assert args.scene == "s.txt"
    assert args.project == "p"


def test_build_parser_supports_sessions_resume_command():
    parser = build_parser()
    args = parser.parse_args(["sessions", "resume", "--project", "p"])

    assert args.command == "sessions"
    assert args.sessions_action == "resume"
    assert args.project == "p"


def test_build_parser_rejects_deprecated_analyze_model_flag():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "analyze",
            "--scene",
            "s.txt",
            "--project",
            "p",
            "--model",
            "sonnet",
        ])


def test_build_parser_rejects_deprecated_analyze_discussion_model_flag():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "analyze",
            "--scene",
            "s.txt",
            "--project",
            "p",
            "--discussion-model",
            "haiku",
        ])


def test_analyze_alias_maps_to_sessions_start():
    parser = build_parser()
    args = parser.parse_args(["analyze", "--scene", "s.txt", "--project", "p"])

    _normalize_focus_area_aliases(args)

    assert args.command == "sessions"
    assert args.sessions_action == "start"


def test_resume_alias_maps_to_sessions_resume():
    parser = build_parser()
    args = parser.parse_args(["resume", "--project", "p"])

    _normalize_focus_area_aliases(args)

    assert args.command == "sessions"
    assert args.sessions_action == "resume"


def test_build_parser_supports_sessions_show_command():
    parser = build_parser()
    args = parser.parse_args(["sessions", "show", "42", "--project", "p"])

    assert args.command == "sessions"
    assert args.sessions_action == "show"
    assert args.id == 42
    assert args.project == "p"


def test_session_config_alias_maps_to_config_action():
    parser = build_parser()
    args = parser.parse_args(["session", "config", "show"])

    _normalize_focus_area_aliases(args)

    assert args.command == "config"
    assert args.config_action == "show"


def test_build_parser_supports_scenes_list_command():
    parser = build_parser()
    args = parser.parse_args(["scenes", "list", "--project", "p"])

    assert args.command == "scenes"
    assert args.scenes_action == "list"
    assert args.project == "p"


def test_build_parser_supports_scenes_lock_command():
    parser = build_parser()
    args = parser.parse_args(["scenes", "lock", "text/ch1.md", "--project", "p"])

    assert args.command == "scenes"
    assert args.scenes_action == "lock"
    assert args.scene_filename == "text/ch1.md"
    assert args.project == "p"


def test_build_parser_supports_scenes_unlock_command():
    parser = build_parser()
    args = parser.parse_args(["scenes", "unlock", "text/ch1.md", "--project", "p"])

    assert args.command == "scenes"
    assert args.scenes_action == "unlock"
    assert args.scene_filename == "text/ch1.md"
    assert args.project == "p"


def test_build_parser_supports_scenes_rename_command():
    parser = build_parser()
    args = parser.parse_args(
        ["scenes", "rename", "text/ch1.md", "text/ch1-renamed.md", "--project", "p"]
    )

    assert args.command == "scenes"
    assert args.scenes_action == "rename"
    assert args.old_filename == "text/ch1.md"
    assert args.new_filename == "text/ch1-renamed.md"
    assert args.project == "p"


def test_build_parser_rejects_removed_indexes_command():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["indexes", "list", "--project", "p"])


def test_build_parser_rejects_removed_index_alias():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["index", "--scene", "s.txt", "--project", "p"])


def test_build_parser_rejects_removed_audit_alias():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["audit", "--project", "p"])


def test_build_parser_supports_learning_list_command():
    parser = build_parser()
    args = parser.parse_args(["learning", "list", "--project", "p"])

    assert args.command == "learning"
    assert args.learning_action == "list"
    assert args.project == "p"


def test_build_parser_supports_learning_add_command():
    parser = build_parser()
    args = parser.parse_args(["learning", "add", "--project", "p"])

    assert args.command == "learning"
    assert args.learning_action == "add"
    assert args.project == "p"


def test_build_parser_supports_learning_update_command():
    parser = build_parser()
    args = parser.parse_args(["learning", "update", "7", "--project", "p"])

    assert args.command == "learning"
    assert args.learning_action == "update"
    assert args.id == 7
    assert args.project == "p"


def test_build_parser_supports_knowledge_refresh_command():
    parser = build_parser()
    args = parser.parse_args(["knowledge", "refresh", "--project", "p"])

    assert args.command == "knowledge"
    assert args.knowledge_action == "refresh"
    assert args.project == "p"


def test_build_parser_supports_knowledge_review_command_with_category():
    parser = build_parser()
    args = parser.parse_args(["knowledge", "review", "characters", "--project", "p"])

    assert args.command == "knowledge"
    assert args.knowledge_action == "review"
    assert args.category == "characters"
    assert args.project == "p"


def test_build_parser_supports_knowledge_export_command_with_output():
    parser = build_parser()
    args = parser.parse_args([
        "knowledge",
        "export",
        "--project",
        "p",
        "--output",
        "p/KNOWLEDGE.md",
    ])

    assert args.command == "knowledge"
    assert args.knowledge_action == "export"
    assert args.project == "p"
    assert args.output == "p/KNOWLEDGE.md"


def test_cmd_knowledge_refresh_prints_chain_warnings_and_extraction(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        "cli.commands.refresh_project_knowledge",
        lambda _project: {
            "scene_updated": 2,
            "scene_total": 3,
            "index_updated": 1,
            "index_total": 2,
            "chain_warnings": [
                {
                    "type": "gap",
                    "scene": "Scenes/ch1.md",
                    "field": "next",
                    "target": "Scenes/ch2.md",
                }
            ],
            "extraction": {
                "attempted": True,
                "model_name": "haiku",
                "scenes_scanned": 2,
                "extracted": [{"scene": "Scenes/ch1.md"}],
                "skipped_locked": [{"scene": "Scenes/ch3.md"}],
                "failed": [],
            },
        },
    )

    args = SimpleNamespace(project=str(tmp_path), knowledge_action="refresh")
    cmd_knowledge(args)
    out = capsys.readouterr().out

    assert "Knowledge refresh complete." in out
    assert "Scenes: 2/3 updated" in out
    assert "Indexes: 1/2 updated" in out
    assert "Chain warnings:" in out
    assert "references missing scene" in out
    assert "Attempted: yes (haiku)" in out
    assert "Scenes scanned: 2" in out
    assert "Extracted: 1" in out
    assert "Skipped (locked): 1" in out


def test_cmd_knowledge_export_writes_default_markdown(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("cli.commands.export_knowledge_markdown", lambda _conn: "# Knowledge Export\n")

    args = SimpleNamespace(project=str(tmp_path), knowledge_action="export", output=None)
    cmd_knowledge(args)

    out = capsys.readouterr().out
    exported = tmp_path / "KNOWLEDGE_EXPORT.md"

    assert "Exported knowledge markdown" in out
    assert exported.exists()
    assert exported.read_text(encoding="utf-8") == "# Knowledge Export\n"
