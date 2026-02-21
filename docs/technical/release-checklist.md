# Release Checklist (No-CI Workflow)

Use this checklist before creating/pushing any release tag.

---

## 1) Decide Scope and SemVer Bumps

- [ ] Identify affected components (`contracts_v1`, `core`, `platform`, `cli`, `web`, `vscode_extension`)
- [ ] Apply SemVer bump per component (MAJOR/MINOR/PATCH)
- [ ] Update `versioning/compatibility.json` component versions
- [ ] If a compatibility boundary changed, update `versioning/compatibility.json` compatibility majors

---

## 2) Propagate Versions to Code/Manifests

- [ ] `contracts/v1/__init__.py` (`__version__`)
- [ ] `core/__init__.py` and `core/api.py` app version
- [ ] `lit_platform/__init__.py` and `pyproject.toml` project version
- [ ] `cli/__init__.py`
- [ ] `web/__init__.py`, `web/app.py`, and web footer versions
- [ ] `vscode-extension/package.json`

---

## 3) Run Local Gates

```bash
npm run release:check
```

- [ ] SemVer validator passes
- [ ] `npm test` (recommended for release candidates)

---

## 3.5) Repo Path Preflight Regression Gate

Run these checks whenever the release includes startup/configuration/touchpoints in CLI, Web, or VS Code extension.

- [ ] Canonical repo preflight validation reason codes still behave as expected (`empty`, `not_found`, `not_directory`, `missing_marker`, valid path).
- [ ] CLI non-interactive mode fails with actionable guidance when repo path is invalid.
- [ ] CLI interactive recovery accepts corrected path and persists it to user config.
- [ ] Web API preflight endpoints behave as documented (`GET /api/repo-preflight`, `POST /api/repo-path`).
- [ ] Web startup-sensitive endpoints return structured `409` with `code=repo_path_invalid` when preflight fails (`/api/analyze`, `/api/resume`, `/api/resume-session`).
- [ ] VS Code repo preflight validator tests pass.
- [ ] VS Code startup recovery flow gets a manual smoke check (invalid path -> Select Folder/Open Settings -> successful retry).

Targeted commands:

```bash
py -3.13 -m pytest tests/platform/test_repo_preflight.py tests/cli/test_repo_preflight_cli.py tests/web/test_routes.py -q
npm --prefix vscode-extension test -- --grep repoPreflight
```

- [ ] Python targeted preflight tests pass.
- [ ] VS Code targeted repoPreflight tests pass.

---

## 4) Create Component Tags

Use component-scoped tags only for changed components.

Examples:

```bash
git tag -a core-v2.0.0 -m "core 2.0.0"
git tag -a platform-v2.0.0 -m "platform 2.0.0"
git tag -a cli-v2.0.0 -m "cli 2.0.0"
```

- [ ] Tag names follow `<component>-vX.Y.Z`
- [ ] Tag versions match `versioning/compatibility.json`

---

## 5) Push

```bash
git push
git push --tags
```

- [ ] Branch pushed
- [ ] Tags pushed
