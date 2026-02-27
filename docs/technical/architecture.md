# Architecture Guide

This document describes the **current canonical architecture** of lit-critic.

lit-critic is organized as three explicit layers:

1. **Core (`core/`)** — stateless reasoning engine
2. **Platform (`lit_platform/`)** — workflow + persistence owner
3. **Clients (`cli/`, `web/`, `vscode-extension/`)** — thin UX layers

---

## 1) Responsibility Boundaries

| Layer | Owns | Must Not Own |
|---|---|---|
| Core | Analyze/discuss/re-evaluate reasoning over versioned contract payloads | Filesystem paths, session lifecycle, SQLite orchestration |
| Platform | Scene/index loading, session state machine, persistence, retry/backoff, Core transport | Client-specific presentation/UI concerns |
| Clients | Interaction, navigation, rendering, command surfaces | Workflow orchestration or direct Core coupling |

---

## 2) Runtime Topology

```text
CLI / Web UI / VS Code
        |
        |  /api/*
        v
Web/API Surface (web/routes.py)
        |
        |  Platform services + facade
        v
Platform (lit_platform/*)
        |
        |  /v1/* contracts
        v
Core (core/api.py)
```

### Deployment modes

- **Default:** all components local (localhost)
- **Remote Core:** Platform stays close to project data; Core can be remote behind TLS + auth gateway

---

## 3) Core (`core/`)

Core is stateless and contract-first.

### Public endpoints

- `GET /health`
- `POST /v1/analyze`
- `POST /v1/discuss`
- `POST /v1/re-evaluate-finding`

### Core characteristics

- Accepts text + structured payloads only
- No direct file or database access
- Returns deterministic, validated contract responses

---

## 4) Platform (`lit_platform/`)

Platform is the workflow boundary and source of orchestration truth.

### Key modules

- `facade.py` — scene/index loading and contract request assembly
- `core_client.py` — transport, timeout, retry/backoff, error mapping
- `context.py` — condensed discussion context generation
- `session_state_machine.py` — state transitions and review behavior helpers
- `persistence/*` — SQLite lifecycle and data access
- `services/*` — session/discussion/learning orchestration services

### Platform guarantees

- Session lifecycle consistency across all clients
- Immediate persistence of user actions
- Moved-scene recovery and scene-change re-evaluation
- Uniform error handling and retry policy

---

## 5) Client Layers

All clients are presentation and interaction layers over Platform behavior.

### CLI (`cli/`)

- Terminal-first review loop
- Commands for analyze/resume/sessions/learning

### Web UI (`web/`)

- HTTP API + HTML/JS interface
- Streaming progress + discussion

### VS Code Extension (`vscode-extension/`)

- Diagnostics, findings tree, discussion panel
- Local API process management for developer workflow

#### Internal module structure

The extension is decomposed into focused modules to keep `extension.ts` as a thin composition root:

| Module | Responsibility |
|---|---|
| `extension.ts` | Activation wiring only — instantiates services, registers commands, delegates startup |
| `bootstrap/startupService.ts` | Repo-root discovery, repo-path recovery, server startup with busy UI, auto-load sidebars, activity-view reveal |
| `commands/registerCommands.ts` | Centralised command-ID → handler mapping; keeps command palette surface enumerable and testable |
| `workflows/sessionWorkflowController.ts` | All session/finding command handlers (analyze, resume, accept, reject, review, rerun, etc.) |
| `workflows/stateStore.ts` | Mutable runtime session state (findings cache, current index, totals, notices) — injected as a unit to enable deterministic tests |
| `ui/workbenchPresenter.ts` | Status bar transitions, findings/sessions tree reveal, discussion panel coordination, diagnostics updates |
| `domain/findingLogic.ts` | Pure finding-navigation helpers (fallback resolution, index clamping, context-change detection) |
| `domain/sessionDecisionLogic.ts` | Pure session-entry decision helpers (repo-path error parsing, session label formatting) |
| `domain/modelSelectionLogic.ts` | Pure model/preset selection helpers (configured model resolution, status message building) |

All VS Code surface interactions are injected through narrow port interfaces (`StartupPorts`, `WorkflowUiPort`, `WorkflowDeps`) so that unit tests can use simple fakes without loading the VS Code runtime.

#### Test organization

| Test file | What it tests |
|---|---|
| `test_startupService.ts` | Startup service branches: repo discovery, recovery loop, progress UI, activity reveal |
| `test_sessionWorkflowController.ts` | Workflow command handlers with fake ports — no VS Code or server required |
| `test_registerCommands.ts` | Command-ID coverage and handler-wiring correctness |
| `test_domain_*.ts` | Pure helper logic — zero mocking |
| `test_extension_real.ts` | Integration-style: activation wiring, command registration, auto-start behavior |

---

## 6) Data Ownership and Persistence

### Filesystem (source of truth)

- Scene text files
- Index files (`CANON.md`, `CAST.md`, `GLOSSARY.md`, `STYLE.md`, `THREADS.md`, `TIMELINE.md`)

### SQLite (`.lit-critic.db`)

Owned by Platform for:

- sessions
- findings
- learning

Key persisted multi-scene fields include:

- session scene set (`scene_paths`)
- per-finding source scene (`finding.scene_path`)

Persistence is auto-applied on each mutation (accept/reject/discuss/navigate).

---

## 7) Core Flows

### Analysis

1. Client starts analysis via `/api/analyze`
2. Platform loads one or more consecutive scenes + indexes
3. Platform concatenates selected scenes and tracks line/source mapping
4. Platform calls Core `/v1/analyze`
5. Results are mapped back to scene-local lines with per-finding `scene_path`
6. Results are persisted and returned to client

### Discussion

1. Client posts message via `/api/finding/discuss` (or streaming variant)
2. Platform builds condensed context + current finding state
3. In multi-scene sessions, discussion scope is constrained to the finding's source scene
4. Platform calls Core `/v1/discuss`
5. Outcome (revised/withdrawn/etc.) is persisted and broadcast to client

### Resume

1. Client requests `/api/resume`
2. Platform restores active session from SQLite
3. Scene hash/path validation runs (with recovery when needed)
4. Review continues from persisted index

---

## 8) Reliability and Security

- Transport retries/backoff are applied by Platform (`core_client.py`)
- Persistence lock contention is handled with bounded retries
- Remote Core deployments require gateway-authenticated TLS
- Clients should reconcile state before replaying mutating actions

See:

- [Reliability Policy](reliability-policy.md)
- [Remote Core Security](security-remote-core.md)

---

## 9) Design Principles

1. **Stateless Core boundary**
2. **Single orchestration owner (Platform)**
3. **Client interoperability through shared persisted state**
4. **Contract-first compatibility**
5. **Local-first data ownership**

---

## 10) See Also

- [API Reference](api-reference.md)
- [Installation Guide](installation.md)
- [Testing Guide](testing.md)
- [Versioning & Compatibility](versioning.md)
- [Reliability Policy](reliability-policy.md)
- [Remote Core Security](security-remote-core.md)
