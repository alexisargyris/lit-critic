from cli.commands import _ensure_repo_path_preflight


def test_repo_preflight_non_interactive_fails(monkeypatch):
    monkeypatch.setenv("LIT_CRITIC_REPO_PATH", "")
    monkeypatch.setattr("cli.commands.get_repo_path", lambda: "")
    monkeypatch.setattr("cli.commands.validate_repo_path", lambda _: type("R", (), {
        "ok": False,
        "message": "Repository path is empty.",
        "path": None,
    })())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    try:
        _ensure_repo_path_preflight()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Repository preflight failed" in str(exc)


def test_repo_preflight_interactive_recovers_and_saves(monkeypatch, tmp_path):
    valid_path = str(tmp_path)
    marker = tmp_path / "lit-critic-web.py"
    marker.write_text("ok", encoding="utf-8")

    saved = {"path": None}

    monkeypatch.setenv("LIT_CRITIC_REPO_PATH", "")
    monkeypatch.setattr("cli.commands.get_repo_path", lambda: "")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    answers = iter([valid_path])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("cli.commands.set_repo_path", lambda path: saved.update({"path": path}))

    def _validate(path):
        if not path:
            return type("R", (), {
                "ok": False,
                "message": "Repository path is empty.",
                "path": None,
            })()
        return type("R", (), {
            "ok": True,
            "message": "Repository path is valid.",
            "path": valid_path,
        })()

    monkeypatch.setattr("cli.commands.validate_repo_path", _validate)

    resolved = _ensure_repo_path_preflight()
    assert resolved == valid_path
    assert saved["path"] == valid_path
