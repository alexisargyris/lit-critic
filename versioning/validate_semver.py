#!/usr/bin/env python3
"""Local SemVer validator for lit-critic componentized architecture.

This script is intentionally CI-agnostic. It is designed to be run locally
during development/release and from Git hooks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _is_semver(value: str) -> bool:
    return bool(SEMVER_RE.fullmatch(value))


def _major(value: str) -> int:
    return int(value.split(".", 1)[0])


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_regex(path: Path, pattern: str, description: str) -> str:
    content = _read_text(path)
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"Could not find {description} in {path}")
    return match.group(1)


def _load_json(path: Path) -> dict:
    return json.loads(_read_text(path))


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    errors: list[str] = []

    compatibility_path = root / "versioning" / "compatibility.json"
    if not compatibility_path.exists():
        print("[ERROR] Missing versioning/compatibility.json")
        return 1

    compatibility = _load_json(compatibility_path)
    components = compatibility.get("components", {})
    compatibility_rules = compatibility.get("compatibility", {})

    required_components = {
        "contracts_v1",
        "core",
        "platform",
        "cli",
        "web",
        "vscode_extension",
    }

    missing = sorted(required_components - set(components.keys()))
    if missing:
        errors.append(f"compatibility.json missing component versions: {', '.join(missing)}")

    for name, version in components.items():
        if not _is_semver(version):
            errors.append(f"components.{name}='{version}' is not valid SemVer")

    # Source-of-truth parity checks across files.
    checks: list[tuple[str, str, str, bool]] = []

    try:
        checks.extend(
            [
                (
                    "contracts/v1/__init__.py",
                    _extract_regex(
                        root / "contracts" / "v1" / "__init__.py",
                        r'__version__\s*=\s*"([^"]+)"',
                        "contracts v1 __version__",
                    ),
                    components.get("contracts_v1", ""),
                    True,
                ),
                (
                    "core/__init__.py",
                    _extract_regex(
                        root / "core" / "__init__.py",
                        r'__version__\s*=\s*"([^"]+)"',
                        "core __version__",
                    ),
                    components.get("core", ""),
                    True,
                ),
                (
                    "core/api.py (FastAPI version)",
                    _extract_regex(
                        root / "core" / "api.py",
                        r'version\s*=\s*(CORE_VERSION)',
                        "core FastAPI app version binding",
                    ),
                    "CORE_VERSION",
                    False,
                ),
                (
                    "lit_platform/__init__.py",
                    _extract_regex(
                        root / "lit_platform" / "__init__.py",
                        r'__version__\s*=\s*"([^"]+)"',
                        "platform __version__",
                    ),
                    components.get("platform", ""),
                    True,
                ),
                (
                    "pyproject.toml [project].version",
                    _extract_regex(
                        root / "pyproject.toml",
                        r'\[project\].*?\nversion\s*=\s*"([^"]+)"',
                        "pyproject project.version",
                    ),
                    components.get("platform", ""),
                    True,
                ),
                (
                    "cli/__init__.py",
                    _extract_regex(
                        root / "cli" / "__init__.py",
                        r'__version__\s*=\s*"([^"]+)"',
                        "cli __version__",
                    ),
                    components.get("cli", ""),
                    True,
                ),
                (
                    "web/__init__.py",
                    _extract_regex(
                        root / "web" / "__init__.py",
                        r'__version__\s*=\s*"([^"]+)"',
                        "web __version__",
                    ),
                    components.get("web", ""),
                    True,
                ),
                (
                    "web/app.py (FastAPI version)",
                    _extract_regex(
                        root / "web" / "app.py",
                        r'version\s*=\s*(WEB_VERSION)',
                        "web FastAPI app version binding",
                    ),
                    "WEB_VERSION",
                    False,
                ),
                (
                    "web/templates/index.html footer",
                    _extract_regex(
                        root / "web" / "templates" / "index.html",
                        r"lit-critic v([^\s]+)",
                        "web index footer version",
                    ),
                    components.get("web", ""),
                    True,
                ),
                (
                    "web/templates/sessions.html footer",
                    _extract_regex(
                        root / "web" / "templates" / "sessions.html",
                        r"lit-critic v([^\s]+)",
                        "web sessions footer version",
                    ),
                    components.get("web", ""),
                    True,
                ),
                (
                    "web/templates/learning.html footer",
                    _extract_regex(
                        root / "web" / "templates" / "learning.html",
                        r"lit-critic v([^\s]+)",
                        "web learning footer version",
                    ),
                    components.get("web", ""),
                    True,
                ),
                (
                    "vscode-extension/package.json",
                    _load_json(root / "vscode-extension" / "package.json").get("version", ""),
                    components.get("vscode_extension", ""),
                    True,
                ),
            ]
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    for source, actual, expected, require_semver in checks:
        if actual != expected:
            errors.append(f"{source} has '{actual}', expected '{expected}'")
        if require_semver and actual and not _is_semver(actual):
            errors.append(f"{source} has non-SemVer value '{actual}'")

    # Root package.json is a tooling manifest; enforce SemVer format only.
    try:
        root_pkg_version = _load_json(root / "package.json").get("version", "")
        if not _is_semver(root_pkg_version):
            errors.append(f"package.json version '{root_pkg_version}' is not valid SemVer")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Failed to read package.json: {exc}")

    # Compatibility matrix major-version rules.
    try:
        platform_rules = compatibility_rules.get("platform", {})
        if platform_rules.get("core_major") != _major(components["core"]):
            errors.append(
                "compatibility.platform.core_major does not match components.core major"
            )
        if platform_rules.get("contracts_v1_major") != _major(components["contracts_v1"]):
            errors.append(
                "compatibility.platform.contracts_v1_major does not match components.contracts_v1 major"
            )

        for client in ("cli", "web", "vscode_extension"):
            client_rules = compatibility_rules.get(client, {})
            if client_rules.get("platform_major") != _major(components["platform"]):
                errors.append(
                    f"compatibility.{client}.platform_major does not match components.platform major"
                )
    except (KeyError, ValueError) as exc:
        errors.append(f"Invalid compatibility matrix: {exc}")

    if errors:
        print("[ERROR] SemVer validation failed:\n")
        for idx, err in enumerate(errors, start=1):
            print(f"  {idx}. {err}")
        print("\nRun: python versioning/validate_semver.py")
        return 1

    print("[OK] SemVer validation passed")
    print("   components + compatibility matrix are internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
