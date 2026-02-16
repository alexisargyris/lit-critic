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
