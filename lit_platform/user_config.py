"""User-level configuration persistence for lit-critic clients."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UserConfig:
    repo_path: str | None = None


def get_user_config_path() -> Path:
    """Return the user-level config file path.

    Uses a platform-appropriate location and supports an override via
    ``LIT_CRITIC_USER_CONFIG_PATH`` for tests.
    """
    override = os.environ.get("LIT_CRITIC_USER_CONFIG_PATH", "").strip()
    if override:
        return Path(override)

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "lit-critic" / "config.json"

    return Path.home() / ".config" / "lit-critic" / "config.json"


def load_user_config() -> UserConfig:
    path = get_user_config_path()
    if not path.exists():
        return UserConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return UserConfig()

    repo_path = data.get("repo_path") if isinstance(data, dict) else None
    if isinstance(repo_path, str):
        repo_path = repo_path.strip() or None
    else:
        repo_path = None
    return UserConfig(repo_path=repo_path)


def save_user_config(config: UserConfig) -> None:
    path = get_user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"repo_path": config.repo_path}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_repo_path() -> str | None:
    return load_user_config().repo_path


def set_repo_path(repo_path: str) -> None:
    save_user_config(UserConfig(repo_path=repo_path.strip() or None))
