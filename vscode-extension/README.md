# lit-critic — VS Code Extension

A VS Code extension for [lit-critic](https://github.com/alexisargyris/lit-critic), the multi-lens editorial review system for fiction manuscripts.

The extension is a thin UI over the **Platform-owned workflow**: it presents findings as diagnostics (squiggly underlines), sidebar tree items, and an interactive discussion panel while Platform handles orchestration, persistence, and Core calls.

## Prerequisites

- **Python 3.10+** with lit-critic installed:
  ```bash
  cd /path/to/lit-critic
  pip install -r requirements.txt
  ```
- **API key** for your chosen provider:
  - Anthropic: `ANTHROPIC_API_KEY`
  - OpenAI: `OPENAI_API_KEY`
  - If analysis and discussion use different providers, configure both keys.
- A fiction project with index files (`CANON.md`, `CAST.md`, etc.)

## Installation

### Development (F5 launch)

```bash
cd vscode-extension
npm install
npm run compile
```

Then open `vscode-extension/` in VS Code and press **F5**.

### VSIX package (regular use)

```bash
cd vscode-extension
npm install
npm run package
```

Install the generated `.vsix`:

```bash
code --install-extension lit-critic-2.3.0.vsix --force
```

## Usage

### 1) Open your project

Open the folder that contains `CANON.md`, `CAST.md`, and scene `.txt` files. The extension activates automatically when `CANON.md` is detected.

When `literaryCritic.autoStartServer` is enabled (default), the extension also auto-reveals the **lit-critic** activity view after startup in `CANON.md` workspaces.

> If your fiction project is outside the lit-critic repository, set `literaryCritic.repoPath` to the lit-critic installation directory (for example `C:\Projects\lit-critic`). See [Opening a Scene Folder](#opening-a-scene-folder-separate-from-the-repo).

### 2) Run analysis

1. Press **`Ctrl+Shift+L`** (or run **lit-critic: Analyze Current Scene**).
2. Use the multi-scene selection UI to choose one or more consecutive scenes (the same UI is used even for single-scene runs).
3. The extension starts the local Platform API process if needed.
4. Platform runs the 5 lenses in parallel (Prose, Structure, Logic, Clarity, Continuity).
5. The Discussion Panel opens with the first finding.

### 3) Review findings

For each finding, you can:

- **Accept**
- **Reject** (optional reason)
- **Discuss** (AI can revise/withdraw/escalate)
- **Skip minor**
- **Navigate to next finding**

The editor, sidebar, and discussion panel stay synchronized.

### 4) Save and resume

- Progress is persisted to your project database (`.lit-critic.db`) by Platform.
- Reopen the project and run Analyze/Resume to continue.
- Export learning anytime via **lit-critic: Save Learning**.

## How It Works

```text
VS Code Extension -- HTTP /api/* --> Web/API surface --> Platform --> Core (/v1/*)
       |                                  |
       |-- diagnostics, tree, panel       |-- workflow, persistence, retries
```

Clients do not orchestrate Core directly; Platform owns the workflow boundary.

## Features

### Diagnostics

- Critical -> red squiggles
- Major -> yellow squiggles
- Minor -> blue squiggles
- Diagnostics are grouped per source file in multi-scene sessions (`finding.scene_path`)

### Sidebar Tree

Findings grouped by lens with click-to-jump navigation.

- Auto-reveals the lit-critic activity view on startup in `CANON.md` projects (when auto-start is enabled)

- **Status-first rendering** so pending/actionable findings stand out immediately
- **Severity tokens** (`[CRIT]`, `[MAJ]`, `[MIN]`) as a compact secondary cue
- **Operational ordering inside each lens**: pending/actionable first, then by severity
- Dedicated status symbols/colors for `pending`, `accepted`, `rejected`, `withdrawn`, `conceded`, `revised`, `discussed`, and `escalated`
- Session labels support scene sets (for example `01.02.01_scene.txt +2`) with full-scene-list tooltips

### Discussion Panel

- Finding details
- Chat-style discussion
- Resizable discussion input (drag the textarea handle to enlarge/shrink)
- Streaming responses
- Re-review context preservation: when scene edits re-evaluate a finding, prior turns are shown as archived context and the updated finding starts a fresh discussion block
- Actions: Accept, Reject, Skip Minor, Export Learning

### Status Bar

- Ready
- Analyzing with progress
- Active review (`current/total`)
- Review complete

### Slow-operation feedback

For operations that can take noticeable time (for example loading a large session, resuming, or refreshing sessions/learning):

- Fast operations stay silent (no flicker/noise)
- Slow operations show a temporary spinning status-bar message
- Very slow operations escalate to a VS Code progress notification
- Timings are logged to the `lit-critic` output channel to help identify bottlenecks

### Scene Change Detection

If one or more reviewed scenes change mid-review, Platform adjusts per-scene line mappings and re-evaluates stale findings automatically.

## Commands

| Command | Keybinding | Description |
|---------|-----------|-------------|
| Analyze Current Scene | `Ctrl+Shift+L` | Start a new analysis |
| Resume Session | — | Resume active session |
| Next Finding | `Ctrl+Shift+]` | Advance |
| Accept Finding | — | Accept current finding |
| Reject Finding | — | Reject current finding |
| Discuss Finding | — | Focus/open panel |
| Skip Minor | — | Skip minor findings |
| Save Session | — | Persist progress |
| Clear Session | — | Delete active session |
| Save Learning | — | Export `LEARNING.md` |
| Select Model | — | Pick analysis model |
| Stop Local API Process | — | Stop local API process |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `literaryCritic.repoPath` | *(empty)* | Absolute path to lit-critic installation (contains `lit-critic-web.py`); required when workspace is outside repo |
| `literaryCritic.pythonPath` | `python` | Python interpreter |
| `literaryCritic.serverPort` | `8000` | Local API process port |
| `literaryCritic.analysisModel` | `sonnet` | Analysis model (`opus`, `sonnet`, `haiku`, `gpt-4o`, `gpt-4o-mini`, `o3`) |
| `literaryCritic.discussionModel` | *(empty)* | Optional discussion model (empty => use analysis model) |
| `literaryCritic.autoStartServer` | `true` | Auto-start local API process on activation |

### Provider keys

- Same provider for analysis/discussion -> one key is enough.
- Different providers -> configure both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.

## Opening a Scene Folder (separate from repo)

1. Open your fiction project folder in VS Code.
2. Set `literaryCritic.repoPath` to your lit-critic install path.
3. Open a scene file and run Analyze.

Workspace settings example:

```json
{
  "literaryCritic.repoPath": "C:\\Projects\\lit-critic"
}
```

## Architecture

```text
vscode-extension/
  src/
    extension.ts
    serverManager.ts
    apiClient.ts
    diagnosticsProvider.ts
    findingsTreeProvider.ts
    discussionPanel.ts
    statusBar.ts
    types.ts
```

The extension is presentation-only; orchestration and persistence are Platform responsibilities.

## Interoperability

The extension interoperates with CLI and Web UI through the same project database (`.lit-critic.db`) and learning export (`LEARNING.md`). You can start in one interface and continue in another.
