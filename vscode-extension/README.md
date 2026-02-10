# lit-critic — VS Code Extension

A VS Code extension for [lit-critic](https://github.com/alexisargyris/lit-critic) (short for Literary Critic), a multi-lens editorial review system. Run editorial reviews directly from within the editor, with findings shown as native VS Code diagnostics (squiggly underlines), a sidebar tree view, and an interactive discussion panel.

## Prerequisites

- **Python 3.10+** with the lit-critic backend installed:
  ```bash
  cd /path/to/lit-critic
  pip install -r requirements.txt
  ```
- **API key** for your chosen AI provider:
  - Anthropic: `ANTHROPIC_API_KEY` environment variable
  - OpenAI: `OPENAI_API_KEY` environment variable
- A fiction project with index files (`CANON.md`, `CAST.md`, etc.)

## Installation

### Development (F5 launch)

```bash
cd vscode-extension
npm install
npm run compile
```

Then open the `vscode-extension` folder in VS Code and press **F5** to launch an Extension Development Host window with the extension loaded.

### VSIX package (install for regular use)

```bash
cd vscode-extension
npm install
npm run package
```

This produces `lit-critic-0.2.0.vsix`. Install it with:

```bash
code --install-extension lit-critic-0.2.0.vsix --force
```

## Usage

### Step 1: Open your project

Open your fiction project folder in VS Code — the folder that contains `CANON.md`, `CAST.md`, and your scene `.txt` files. The extension activates automatically when it detects `CANON.md`.

> **Scene folder outside the repo?** If your fiction project lives in a separate folder from the lit-critic installation (the typical setup), you must tell the extension where to find the backend. Open **Settings** (`Ctrl+,`), search for `literaryCritic.repoPath`, and set it to the absolute path of the lit-critic directory (e.g. `C:\Projects\lit-critic`). See [Opening a Scene Folder](#opening-a-scene-folder-separate-from-the-repo) for details.

### Step 2: Run an analysis

1. Open a scene `.txt` file in the editor.
2. Press **`Ctrl+Shift+L`** (or open the Command Palette with `Ctrl+Shift+P` and run **lit-critic: Analyze Current Scene**).
3. The backend server starts automatically, then runs 5 editorial lenses in parallel (Prose, Structure, Logic, Clarity, Continuity).
4. The status bar shows live progress as each lens completes (30–90 seconds depending on scene length and model).
5. When done, a notification shows the total findings, and the **Discussion Panel** opens with the first finding.

### Step 3: Review findings

Findings are presented **one at a time** in the Discussion Panel (a webview that opens beside your editor). Each finding shows:

- **Severity** 🔴 Critical, ⚠️ Major, or ℹ️ Minor
- **Lens** which editorial lens flagged it (Prose, Structure, etc.)
- **Location** line range in the scene
- **Evidence** the specific text or pattern the lens found
- **Impact** why it matters for the reader
- **Suggestions** concrete options for fixing it

Meanwhile:
- The **editor** shows squiggly underlines at the finding locations (red/yellow/blue by severity).
- The **sidebar tree** (click the lit-critic icon in the Activity Bar) lists all findings grouped by lens.
- The **status bar** shows your progress (e.g. `📖 3/12 findings`).

### Step 4: Act on each finding

For each finding, you can:

| Action | How | What it does |
|--------|-----|-------------|
| **Accept** | Click Accept in the Discussion Panel, or Command Palette → Accept Finding | Marks the finding as accepted; removes the squiggly underline. |
| **Reject** | Click Reject (you can provide an optional reason) | Marks as rejected; removes the underline. The reason is saved for learning. |
| **Discuss** | Type a message in the Discussion Panel chat box | Opens a conversation with the AI about the finding. The AI can revise, withdraw, or escalate the finding based on your arguments. |
| **Next** | `Ctrl+Shift+]` or click Next | Skip to the next finding without acting. |
| **Skip Minor** | Command Palette → Skip Minor Findings | Skip all remaining minor-severity findings and focus on critical/major ones. |

After each action, the next finding is presented automatically.

### Step 5: Save your work

- **Save Session** (`Ctrl+Shift+P` → lit-critic: Save Session) — saves all progress to disk so you can close VS Code and resume later.
- **Resume Session** when you re-open the project and run Analyze, the extension detects the saved session and offers to resume.
- **Save Learning** (`Ctrl+Shift+P` → lit-critic: Save Learning) — writes a `LEARNING.md` file capturing patterns from your accept/reject decisions, so future reviews are calibrated to your style.

### Step 6: When you're done

Once all findings have been reviewed, the extension shows "Review complete". You can:
- Run another analysis on a different scene file
- Stop the backend server via Command Palette → **lit-critic: Stop Server**

---

## How It Works

The extension reuses the **existing FastAPI backend** (the same REST API the Web UI uses). On activation, it spawns `python lit-critic-web.py` as a child process and communicates via HTTP.

```
VS Code Extension --- HTTP ---> FastAPI Backend (localhost:8000)
    |                                |
    |-- Diagnostics (squiggles)      |-- 5 parallel lenses
    |-- Sidebar tree view            |-- Coordinator
    |-- Discussion panel (webview)   |-- Discussion engine
    '-- Status bar                   '-- Session & learning
```

## Features

### Diagnostics (squiggly underlines)

Findings appear as native VS Code diagnostics in the editor:
- **Critical** -> red squiggly (Error)
- **Major** -> yellow squiggly (Warning)
- **Minor** -> blue squiggly (Information)

Each diagnostic includes the evidence, impact, and suggestions in its tooltip. Diagnostics are removed as you accept, reject, or withdraw findings.

### Sidebar Tree View

The **lit-critic** sidebar shows all findings grouped by lens (Prose, Structure, Logic, Clarity, Continuity). Each finding shows its severity, status, and line range. **Click any finding** to jump to that line in the editor AND open the Discussion Panel for it — you can review findings in any order, not just sequentially.

### Discussion Panel

A webview panel opens beside the editor with:
- Finding details (severity, lens, location, evidence, impact, suggestions)
- Chat-style interface for discussing the finding with the AI
- Streaming responses (token-by-token)
- Action buttons: Accept, Reject, Next, Skip Minor, Save Session
- Ambiguity buttons (Intentional/Accidental) for ambiguity findings

### Status Bar

Shows analysis progress and review status:
- `$(book) lit-critic` -- ready, click to analyze
- `$(sync~spin) Analyzing...` -- analysis in progress with live lens status
- `$(book) 3/12 findings` -- active review session
- `$(book) Review complete` -- all findings processed

### Scene Change Detection

If you edit the scene file during a review, the backend automatically detects the change, adjusts line numbers, and re-evaluates any stale findings. The extension displays scene change notifications in the discussion panel.

## Commands

| Command | Keybinding | Description |
|---------|-----------|-------------|
| **Analyze Current Scene** | `Ctrl+Shift+L` | Run a new multi-lens analysis on the active file |
| **Resume Session** | -- | Resume a previously saved session |
| **Next Finding** | `Ctrl+Shift+]` | Advance to the next finding |
| **Accept Finding** | -- | Accept the current finding |
| **Reject Finding** | -- | Reject with optional reason |
| **Discuss Finding** | -- | Open/focus the discussion panel |
| **Skip Minor** | -- | Skip all minor-severity findings |
| **Save Session** | -- | Save progress to resume later |
| **Clear Session** | -- | Delete saved session |
| **Save Learning** | -- | Save LEARNING.md to project |
| **Select Model** | -- | Choose Claude model (Opus/Sonnet/Haiku) |
| **Stop Server** | -- | Stop the backend server |

Access commands via the Command Palette (`Ctrl+Shift+P`), or use the keyboard shortcuts.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `literaryCritic.repoPath` | *(empty)* | Absolute path to the lit-critic installation directory (the folder containing `lit-critic-web.py`). **Required** when your scene folder is not inside the lit-critic repo. |
| `literaryCritic.pythonPath` | `python` | Path to Python interpreter |
| `literaryCritic.serverPort` | `8000` | Port for the backend server |
| `literaryCritic.model` | `sonnet` | Default model (`opus`, `sonnet`, `haiku`, `gpt-4o`, `gpt-4o-mini`) |
| `literaryCritic.autoStartServer` | `true` | Auto-start the backend on activation |

## Activation

The extension activates automatically when a workspace contains a `CANON.md` file (indicating a literary project), or when you invoke any `literaryCritic.*` command.

## Opening a Scene Folder (separate from the repo)

If your fiction project (the folder with `CANON.md`, `CAST.md`, scene files, etc.) lives **outside** the lit-critic repository — which is the typical setup — you need one extra configuration step:

### Quick setup

1. **Open your scene folder** in VS Code (`File → Open Folder…`).
2. The extension activates (it detects `CANON.md`) and the **lit-critic** icon appears in the Activity Bar.
3. Open **Settings** (`Ctrl+,`) and search for `literaryCritic.repoPath`.
4. Set it to the absolute path where you cloned/installed lit-critic, e.g.:
   - Windows: `C:\Projects\lit-critic`
   - macOS/Linux: `/home/you/lit-critic`
5. Open a scene `.txt` file and run **lit-critic: Analyze Current Scene** (`Ctrl+Shift+L`).

> **Tip:** You can also set this in your workspace `.vscode/settings.json`:
> ```json
> {
>   "literaryCritic.repoPath": "C:\\Projects\\lit-critic"
> }
> ```

### Why is this needed?

The extension spawns the lit-critic backend server (`lit-critic-web.py`) as a child process. When your scene folder is inside the lit-critic repo tree, the extension can find the script automatically by walking up the directory tree. When the scene folder is elsewhere, you need to tell it where the backend lives.

If you forget this step, the extension will show a helpful error with an **"Open Settings"** button when you try to analyze a scene.

## Architecture

```
vscode-extension/
  src/
    extension.ts           # Entry point, command registration, orchestration
    serverManager.ts       # Spawns/stops the FastAPI backend process
    apiClient.ts           # Typed HTTP wrapper for all REST endpoints
    diagnosticsProvider.ts # Maps findings -> VS Code Diagnostic squiggles
    findingsTreeProvider.ts# Sidebar tree view grouped by lens
    discussionPanel.ts     # Webview panel for interactive discussion
    statusBar.ts           # Status bar progress indicator
    types.ts               # TypeScript interfaces mirroring Python models
  package.json             # Extension manifest
  tsconfig.json            # TypeScript configuration
```

The extension is a thin presentation layer -- all analysis, coordination, discussion, session management, and learning happen in the shared Python backend.

## Interoperability

The extension shares session files (`.lit-critic-session.json`) and `LEARNING.md` with the CLI and Web UI. You can start a review in the extension, save the session, and resume it from the CLI or Web UI (or vice versa).
