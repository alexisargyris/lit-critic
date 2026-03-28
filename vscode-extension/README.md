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
  - If your configured model slots use different providers, configure both keys.
- A fiction project with `CANON.md`, `STYLE.md`, and scene files. Auto-extracted knowledge categories (Cast, Glossary, Threads, Timeline) are stored in the project database and reviewed from the extension UI.

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
code --install-extension lit-critic-x.y.z.vsix --force
```

Replace x, y, and z with the actual version numbers.

## Usage

### 1) Open your project

Open the folder that contains `CANON.md`, `STYLE.md`, and your scene files. The extension activates automatically when `CANON.md` is detected.

When `literaryCritic.autoStartServer` is enabled (default), the extension also auto-reveals the **lit-critic** activity view after startup in `CANON.md` workspaces.

> If your fiction project is outside the lit-critic repository, set `literaryCritic.repoPath` to the lit-critic installation directory (for example `C:\Projects\lit-critic`). See [Opening a Scene Folder](#opening-a-scene-folder-separate-from-repo).

### 2) Run analysis

1. Press **`Ctrl+Shift+L`** (or run **lit-critic: Analyze**).
2. Use the multi-scene selection UI to choose one or more consecutive scenes (the same UI is used even for single-scene runs).
3. To change analysis depth quickly, use the **Config** button in the **Sessions** view title bar, then pick `quick` or `deep`.
4. The extension starts the local Platform API process if needed.
5. `quick`/`deep` run all 7 lenses in parallel (Prose, Structure, Logic, Clarity, Continuity, Dialogue, Horizon) with tiered model-slot routing (`frontier` + checker slot by mode). Deterministic code checks run automatically as Phase 1 of every analysis.
6. For `quick`/`deep`, the Discussion Panel opens with the first finding.

### Focus Areas

VS Code follows the same canonical focus areas used across clients:

- **Sessions**: Config, Analyze, Refresh Sessions
- **Knowledge**: Refresh Knowledge, Review Knowledge

Command Palette titles for the canonical actions:

| Canonical action | VS Code command title |
|---|---|
| **Config** | `lit-critic: Config` |
| **Analyze** | `lit-critic: Analyze` |
| **Refresh Sessions** | `lit-critic: Refresh Sessions` |
| **Refresh Knowledge** | `lit-critic: Refresh Knowledge` |
| **Review Knowledge** | `lit-critic: Review Knowledge` |

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
- On resume/view, scene files are ensured open without reopening files that are already open in any editor group.
- Export learning anytime via **lit-critic: Export Learning to LEARNING.md**.

### 5) Review and correct extracted knowledge

The **Knowledge** view is the primary browsing surface for extracted Cast, Glossary, Threads, and Timeline data.

- **Refresh Knowledge** updates extracted knowledge from changed scenes.
- **Review Knowledge** loads the current knowledge review tree.
- Click an entity, or use **Open Knowledge Review Panel** from its context menu, for the detailed comparison flow.
- Use **Reset Knowledge Override** to remove an author correction and return to the extracted value.
- Use **Delete Knowledge Entity** to remove an entity permanently. Run **Refresh Knowledge** to re-extract it.
- Use **Toggle Knowledge Lock** to prevent a scene's knowledge from being re-extracted automatically.

`CANON.md` and `STYLE.md` remain normal files edited in the editor. Knowledge overrides apply only to the auto-extracted categories.

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

The activity bar has five views: **Inputs**, **Knowledge**, **Sessions**, **Findings**, and **Learning**.

#### Findings view

Findings grouped by lens with click-to-jump navigation.

- Auto-reveals the lit-critic activity view on startup in `CANON.md` projects (when auto-start is enabled)
- **Status-first rendering** so pending/actionable findings stand out immediately
- **Severity tokens** (`[CRIT]`, `[MAJ]`, `[MIN]`) as a compact secondary cue
- **Operational ordering inside each lens**: pending/actionable first, then by severity
- Dedicated status symbols/colors for `pending`, `accepted`, `rejected`, `withdrawn`, `conceded`, `revised`, `discussed`, and `escalated`
- Session labels support scene sets (for example `01.02.01_scene.txt +2`) with full-scene-list tooltips

#### Knowledge view

The extension exposes a **Knowledge** tree for extracted entities:

- grouped by category (`characters`, `terms`, `threads`, `timeline`)
- quick-edit via context menu actions
- context actions: **Reset Knowledge Override**, **Delete Knowledge Entity**, **Toggle Knowledge Lock**, **Open Knowledge Review Panel**

##### Visual states

Each entity is color-coded and labeled by state. When multiple states apply, the highest-priority state determines the icon and color.

| State | Icon | Label | Color | What to do |
|---|---|---|---|---|
| Stale | ⚠ warning | `stale` | red | Run **Refresh Knowledge** |
| Flagged | ⚠ warning | `flagged` | orange | Use inline Keep ✓ or Delete 🗑 buttons |
| Locked | lock | `locked` | gold | Unlock to allow future LLM updates |
| Overridden | property | `overridden` | teal | Review; reset if extraction corrected itself |
| Normal | property | — | default | No action needed |

**Priority order:** stale → flagged → locked → overridden

##### Flagged entities

After **Refresh Knowledge**, the reconciliation pass may flag entities that appear unsupported by the current text. A notification reports the count. Flagged entities show inline **Keep** and **Delete** buttons in the tree:

- **Keep ✓** — choose **Keep & Lock** (prevents future LLM updates) or **Keep Only** (dismisses the flag without locking).
- **Delete 🗑** — permanently removes the entity and all its overrides after confirmation.

Either action clears the flag immediately.

### Knowledge Review Panel

- Extracted value vs. override value comparison for each editable field
- Per-field save and reset actions
- Next/previous entity navigation without leaving the panel
- Tree refresh after writes so the panel and tree stay synchronized

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
| `lit-critic: Analyze` | `Ctrl+Shift+L` | Start a new analysis |
| `lit-critic: Config` | — | Configure analysis mode (`quick`, `deep`) |
| `lit-critic: Refresh Sessions` | — | Refresh the Sessions tree view |
| `lit-critic: View Session Details` | — | Load a session for viewing from the Sessions tree |
| `lit-critic: Delete Session` | — | Delete a session |
| `lit-critic: Accept Finding` | — | Accept current finding |
| `lit-critic: Reject Finding` | — | Reject current finding |
| `lit-critic: Discuss Finding` | — | Focus/open the Discussion panel |
| `lit-critic: Review Current Finding` | — | Re-check current finding against scene edits |
| `lit-critic: Refresh Inputs` | — | Refresh the Inputs (scenes) tree view |
| `lit-critic: Refresh Knowledge` | — | Refresh extracted project knowledge |
| `lit-critic: Review Knowledge` | — | Load the Knowledge review tree |
| `lit-critic: Reset Knowledge Override` | — | Remove an override from a knowledge entity |
| `lit-critic: Delete Knowledge Entity` | — | Delete an extracted knowledge entity |
| `lit-critic: Toggle Knowledge Lock` | — | Lock/unlock a knowledge entity from re-extraction |
| `lit-critic: Keep Flagged Entity` | — | Keep a flagged knowledge entity as-is |
| `lit-critic: Delete Flagged Entity` | — | Delete a flagged knowledge entity |
| `lit-critic: Open Knowledge Review Panel` | — | Open the detailed Knowledge review panel |
| `lit-critic: Next Knowledge Entity` | — | Move to the next entity in the Knowledge review panel |
| `lit-critic: Previous Knowledge Entity` | — | Move to the previous entity in the Knowledge review panel |
| `lit-critic: Export Learning to LEARNING.md` | — | Export `LEARNING.md` |
| `lit-critic: Refresh Learning Data` | — | Refresh the Learning tree view |
| `lit-critic: Reset All Learning Data` | — | Delete all learning entries |
| `lit-critic: Delete Learning Entry` | — | Delete a single learning entry |
| `lit-critic: Stop Server` | — | Stop local API process |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `literaryCritic.repoPath` | *(empty)* | Absolute path to lit-critic installation (contains `lit-critic-web.py`); required when workspace is outside repo |
| `literaryCritic.pythonPath` | `python` | Python interpreter |
| `literaryCritic.serverPort` | `8000` | Local API process port |
| `literaryCritic.analysisMode` | `deep` | Analysis depth mode for new sessions (`quick`, `deep`) |
| `literaryCritic.modelSlotFrontier` | *(empty)* | Frontier model slot override (critic tasks); empty uses backend default |
| `literaryCritic.modelSlotDeep` | *(empty)* | Deep checker slot override; empty uses backend default |
| `literaryCritic.modelSlotQuick` | *(empty)* | Quick checker slot override; empty uses backend default |
| `literaryCritic.sceneFolder` | `text` | Scene folder (relative to project root) used for scene discovery and refresh watchers |
| `literaryCritic.sceneExtensions` | `["txt"]` | Scene file extensions (without dots) used for scene discovery |
| `literaryCritic.autoStartServer` | `true` | Auto-start local API process on activation |
| `literaryCritic.disableProblemDecorationColors` | `false` | Suppress diagnostic color tinting in file/tab labels (affects all diagnostics in this workspace) |
| `literaryCritic.disableProblemDecorationBadges` | `false` | Suppress problem badges in file/tab labels (affects all diagnostics in this workspace) |
| `literaryCritic.knowledgeReviewPassTrigger` | `always` | Controls when the knowledge reconciliation review pass runs after a refresh (`always`, `on_stale`, `never`) |

### Provider keys

- Same provider across configured model slots -> one key is enough.
- Different providers across slots -> configure both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.

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
