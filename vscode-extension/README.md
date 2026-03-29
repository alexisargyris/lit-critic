# lit-critic — VS Code Extension

An AI editorial assistant for novel writers, running directly inside VS Code.

The extension integrates with the lit-critic review system: it shows findings as squiggly underlines in your scene files, presents them in a sidebar tree, and opens a discussion panel where you can accept, reject, or debate each one — all without leaving your editor.

---

## Prerequisites

- **Python 3.10+** with lit-critic installed:
  ```bash
  cd /path/to/lit-critic
  pip install -r requirements.txt
  ```
- **An API key** for your chosen AI provider:
  - Anthropic: `ANTHROPIC_API_KEY`
  - OpenAI: `OPENAI_API_KEY`
- A novel project folder containing `CANON.md`, `STYLE.md`, and scene files

---

## Installation

### VSIX package (regular use)

```bash
cd vscode-extension
npm install
npm run package
code --install-extension lit-critic-*.vsix --force
```

### Development (F5 launch)

```bash
cd vscode-extension
npm install
npm run compile
```

Open `vscode-extension/` in VS Code and press **F5**.

---

## Usage

### 1. Open your project

Open the folder that contains `CANON.md`. The extension activates automatically when `CANON.md` is detected.

> **If your novel project is outside the lit-critic installation folder**, set `literaryCritic.repoPath` in VS Code Settings to the full path of the lit-critic directory (the one containing `lit-critic-web.py`).

### 2. Run analysis

Press **`Ctrl+Shift+L`** or run `lit-critic: Analyze` from the Command Palette.

Select one or more consecutive scenes in the scene selector. The extension starts the local server automatically and runs all seven lenses in parallel (~30–90 seconds).

### 3. Review findings

Findings appear as squiggly underlines (red = critical, yellow = major, blue = minor) and in the **Findings** sidebar. The **Discussion Panel** opens with the first finding.

For each finding:
- **Accept** — agree, mark resolved
- **Reject** — disagree, optionally provide a reason
- **Discuss** — type a message; the AI responds and may revise or withdraw
- **Skip** — move on without deciding

### 4. Save and resume

Progress is saved automatically after every action. To resume a session: press `Ctrl+Shift+L` — the tool offers to pick up where you left off. If you've moved your project folder, it will prompt for the new path.

### 5. Refresh knowledge

After writing or revising scenes, click **Refresh Knowledge** in the Knowledge view toolbar to extract updated characters, terms, threads, and timeline entries from your prose.

---

## Key commands

| Command | Keybinding | Description |
|---------|-----------|-------------|
| `lit-critic: Analyze` | `Ctrl+Shift+L` | Start a new analysis session |
| `lit-critic: Config` | — | Set analysis mode (quick / deep) |
| `lit-critic: Refresh Knowledge` | — | Extract knowledge from changed scenes |
| `lit-critic: Export Learning to LEARNING.md` | — | Export your preference history |
| `lit-critic: Stop Server` | — | Stop the local API process |

---

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `literaryCritic.repoPath` | *(empty)* | Path to lit-critic installation — required when your novel project is outside the repo |
| `literaryCritic.pythonPath` | `python` | Python interpreter |
| `literaryCritic.serverPort` | `8000` | Local API server port |
| `literaryCritic.analysisMode` | `deep` | Default analysis mode (`quick` or `deep`) |
| `literaryCritic.modelSlotFrontier` | *(empty)* | Frontier model override (empty = use backend default) |
| `literaryCritic.modelSlotDeep` | *(empty)* | Deep checker model override |
| `literaryCritic.modelSlotQuick` | *(empty)* | Quick checker model override |
| `literaryCritic.sceneFolder` | `text` | Subfolder within the project to scan for scene files |
| `literaryCritic.sceneExtensions` | `["txt"]` | File extensions treated as scene files |
| `literaryCritic.autoStartServer` | `true` | Auto-start the local API server on activation |
| `literaryCritic.knowledgeReviewPassTrigger` | `always` | When the reconciliation review pass runs after a refresh |

---

## Interoperability

The extension shares the same project database (`.lit-critic.db`) with the CLI and Web UI. Start a review in VS Code and continue it from the terminal or browser — everything stays in sync.

---

## Full documentation

→ **[Author's User Guide](../docs/user-guide/README.md)** — setup, first review, findings, knowledge, learning system
