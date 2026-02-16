#!/usr/bin/env python3
"""Guardrail for release intent in no-CI workflows.

Fails when component files changed in outgoing commits but
``versioning/compatibility.json`` was not updated.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


COMPATIBILITY_FILE = "versioning/compatibility.json"

COMPONENT_PREFIXES: dict[str, tuple[str, ...]] = {
    "contracts_v1": ("contracts/v1/",),
    "core": ("core/",),
    "platform": ("lit_platform/", "pyproject.toml"),
    "cli": ("cli/", "lit-critic.py"),
    "web": ("web/", "lit-critic-web.py"),
    "vscode_extension": ("vscode-extension/",),
}


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _git_ok(args: list[str]) -> bool:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return proc.returncode == 0


def _changed_files_from_range(diff_range: str) -> list[str]:
    out = _run_git(["diff", "--name-only", diff_range])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _changed_files_from_head_commit() -> list[str]:
    out = _run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _detect_outgoing_files() -> tuple[list[str], str]:
    # 1) Best: upstream tracking branch range.
    if _git_ok(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]):
        upstream = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        return _changed_files_from_range(f"{upstream}...HEAD"), f"{upstream}...HEAD"

    # 2) Fallback: merge-base against origin/main|origin/master.
    for remote_ref in ("origin/main", "origin/master"):
        if _git_ok(["rev-parse", "--verify", remote_ref]):
            base = _run_git(["merge-base", "HEAD", remote_ref])
            return _changed_files_from_range(f"{base}..HEAD"), f"{base}..HEAD (merge-base with {remote_ref})"

    # 3) Last-resort fallback: only latest commit.
    return _changed_files_from_head_commit(), "HEAD (latest commit only fallback)"


def _component_for_path(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    for component, prefixes in COMPONENT_PREFIXES.items():
        for prefix in prefixes:
            if normalized.startswith(prefix) or normalized == prefix:
                return component
    return None


def main() -> int:
    if os.environ.get("LIT_CRITIC_SKIP_RELEASE_INTENT") == "1":
        print("[WARN] Release-intent check skipped (LIT_CRITIC_SKIP_RELEASE_INTENT=1)")
        return 0

    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / COMPATIBILITY_FILE).exists():
        print(f"[ERROR] Missing {COMPATIBILITY_FILE}")
        return 1

    try:
        changed_files, source_range = _detect_outgoing_files()
    except RuntimeError as exc:
        print(f"[ERROR] Release-intent check failed while inspecting git state: {exc}")
        return 1

    touched_components: set[str] = set()
    for rel_path in changed_files:
        component = _component_for_path(rel_path)
        if component:
            touched_components.add(component)

    if not touched_components:
        print(f"[OK] Release-intent check passed (no component changes in {source_range})")
        return 0

    normalized_files = {p.replace('\\', '/') for p in changed_files}
    compatibility_touched = COMPATIBILITY_FILE in normalized_files

    print(f"[INFO] Component changes detected in {source_range}: {', '.join(sorted(touched_components))}")

    if compatibility_touched:
        print(f"[OK] Release-intent check passed ({COMPATIBILITY_FILE} was updated)")
        return 0

    print("[ERROR] Release-intent check failed.")
    print(f"   Component files changed, but {COMPATIBILITY_FILE} was not updated.")
    print("   Suggested next steps:")
    print(f"   1) Update {COMPATIBILITY_FILE} components for: {', '.join(sorted(touched_components))}")
    print("   2) Adjust compatibility majors if boundaries changed")
    print("   3) Run: npm run release:check")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
