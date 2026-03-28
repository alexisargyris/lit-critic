# Using the Tool

lit-critic offers three interfaces for reviewing your scenes. Choose the one that fits your workflow.

---

## CLI (Command Line Interface)

The terminal-based interface. Fast, keyboard-driven, and scriptable.

### Focus Areas

CLI commands use a noun-first structure organized around four canonical buckets:

- **Knowledge**: `refresh`, `review`, `export`
- **Scenes**: `list`, `lock`, `unlock`, `rename`
- **Sessions**: `start`, `resume`, `list`, `show`, `delete`
- **Learning**: `list`, `add`, `update`, `export`, `reset`

Model slot configuration is available as a top-level command group: `config show` and `config set`.

```bash
python -m cli knowledge refresh --project path/to/project/
python -m cli knowledge review --project path/to/project/ --category characters
python -m cli sessions start --scene path/to/scene.txt --project path/to/project/ --mode quick
python -m cli scenes list --project path/to/project/
python -m cli scenes lock scene.txt --project path/to/project/
python -m cli scenes rename old.txt new.txt --project path/to/project/
```

Semantics:
- **Knowledge refresh** = validate scene chain + extract knowledge from changed scenes
- **Sessions start (`--mode quick|deep`)** = full scene analysis workflow (triggers `knowledge refresh` first)

### Cross-client Focus Areas map

All clients align around the same four buckets:

| Bucket | CLI | Web UI | VS Code |
|---|---|---|---|
| **Knowledge** | `knowledge refresh/review/export` | Knowledge refresh + review flows | Knowledge tree view + refresh/review commands |
| **Scenes** | `scenes list/lock/unlock/rename` | Scene list + lock/rename flows | Scenes tree view + scene management commands |
| **Sessions** | `sessions start/resume/list/show/delete` | Session start/resume/history flows | Analyze/resume/session tree workflows |
| **Learning** | `learning list/add/update/export/reset` | Learning list/export/reset flows | Learning tree + learning management commands |

### Basic Usage

```bash
python -m cli sessions start --scene path/to/scene.txt --project path/to/project/
```

### Analysis Mode (`--mode`)

Choose analysis depth mode per run:

```bash
python -m cli sessions start --scene scene.txt --project C:/novel --mode quick
python -m cli sessions start --scene scene.txt --project C:/novel --mode deep
```

- `quick`: full lens pipeline using the quick checker slot
- `deep`: full lens pipeline using the deep checker slot (default)

### Configure Model Slots

Mode chooses depth; slots choose which model each tier uses.

```bash
python -m cli config show
python -m cli config set frontier=sonnet deep=sonnet quick=haiku
```

CLI analysis is single-scene per run. For consecutive multi-scene analysis in one session, use the Web UI or VS Code extension selector.

### Interactive Commands

During review:

| Command | Action |
|---------|--------|
| **Enter** (or `continue`, `c`) | Next finding |
| `skip minor` | Skip all minor findings |
| `skip to structure` | Jump to Structure lens |
| `skip to coherence` | Jump to Coherence lens |
| `quit` (or `q`) | End session |
| `export learning` | Export `LEARNING.md` from current DB-backed learning |
| `help` | Show commands |
| **Type anything else** | Discuss the current finding |

### Special Commands

For ambiguity findings:
- `intentional` Mark as deliberate choice
- `accidental` Mark as unintended

---

## Web UI

A visual interface that runs in your browser.

### Starting the Web UI

```bash
python lit-critic-web.py
```

Then open http://localhost:8000 in your browser.

### Options

```bash
python lit-critic-web.py --port 3000        # Custom port
python lit-critic-web.py --reload            # Auto-reload for development
```

### Features

- **Setup screen** Select scene file(s), project directory, and analysis mode
- **Multi-scene analysis** Use "Add another scene" to select consecutive scenes for cross-boundary analysis
- **Live progress** Watch each lens complete in real-time
- **Chat interface** Discuss findings naturally
- **Action buttons** Accept, Reject, Next, Skip Minor
- **Source scene badges** In multi-scene sessions, each finding shows which scene it belongs to
- **Session persistence** Your mode choice and paths are remembered

### Workflow

1. **Select files** on the setup screen (use "Add another scene" for consecutive multi-scene analysis)
2. **Choose analysis mode** (`quick` or `deep`)
3. **Start analysis** progress bars show each lens
4. **Review findings** one at a time — source scene is shown for multi-scene sessions
5. **Save learning** to capture your preferences

---

## VS Code Extension

Native editor integration with squiggly underlines, sidebar tree, and discussion panel.

### Installation

```bash
cd vscode-extension
npm install
npm run package
code --install-extension lit-critic-2.5.0.vsix --force
```

Or press **F5** in the `vscode-extension` folder for development mode.

### Setup

1. **Open your novel project** in VS Code (the folder with `CANON.md`)
2. **Set repo path** (if your novel is outside the lit-critic installation):
   - Open Settings (`Ctrl+,`)
   - Search for `literaryCritic.repoPath`
   - Set to the absolute path of the lit-critic directory
3. **Optional: reduce diagnostic color noise**
   - Enable `literaryCritic.disableProblemDecorationColors` to suppress diagnostic-based tab/file tinting in this workspace
   - Enable `literaryCritic.disableProblemDecorationBadges` to hide problem badges in this workspace

> These options update VS Code workspace settings under `workbench.editor.decorations.*` and therefore affect **all** diagnostics in that workspace (not only lit-critic).

4. **(Optional) Configure analysis mode and model slots**
   - `literaryCritic.analysisMode`: `quick` or `deep`
   - `literaryCritic.modelSlotFrontier`: model used for frontier/discussion tier
   - `literaryCritic.modelSlotDeep`: model used by deep checker tier
   - `literaryCritic.modelSlotQuick`: model used by quick checker tier

### Usage

1. **Press `Ctrl+Shift+L`** (or Command Palette → "lit-critic: Analyze Current Scene")
2. **If no scene file is open**, pick one from the file dialog that appears
3. **Use the scene-set selector** to choose one or more consecutive scenes (same UI is used for single-scene runs)
4. **Wait for analysis** (status bar shows progress)
5. **Review findings** in the Discussion Panel

### Features

#### Squiggly Underlines
Findings appear as diagnostics in the editor:
- **Red** (Error) — Critical severity
- **Yellow** (Warning) — Major severity
- **Blue** (Info) — Minor severity

Depending on your VS Code theme/settings, diagnostics may also tint the scene file label/tab color. This is VS Code behavior from problem decorations (not a custom color set by lit-critic).

Hover over the underline to see evidence, impact, and suggestions.

#### Sidebar Tree View
Click the **lit-critic** icon in the Activity Bar to see all findings grouped by lens. Click any finding to jump to it.

#### Discussion Panel
A webview beside your editor with:
- Finding details
- Chat interface for discussion
- Action buttons (Accept, Reject, Next)
- Streaming responses

#### Status Bar
Shows progress:
- `$(book) lit-critic` ready
- `$(sync~spin) Analyzing...` running
- `$(book) 3/12 findings` active review

### Commands

| Command | Keybinding | Action |
|---------|-----------|--------|
| Analyze Current Scene | `Ctrl+Shift+L` | Start new analysis (includes knowledge refresh) |
| Refresh Knowledge | — | Refresh extracted knowledge from scenes |
| Review Knowledge | — | Open Knowledge view to inspect/correct extracted entities |
| Next Finding | `Ctrl+Shift+]` | Advance to next finding (internal) |
| Accept Finding | — | Accept current finding |
| Reject Finding | — | Reject with reason |
| Review Current Finding | — | Re-check finding against scene edits |
| View Session | — | Open a session from the Sessions tree |
| Delete Session | — | Delete a session |
| Export Learning to LEARNING.md | — | Export LEARNING.md |
| Select Model | — | Choose analysis mode and model slots |
| Stop Server | — | Stop the local API process |

### Interoperability

The extension shares the same SQLite database (`.lit-critic.db`) with the CLI and Web UI. Start a review in one interface, close it, and resume in another — everything is automatically saved.

### Knowledge context changes

If you edit `CANON.md`, `STYLE.md`, or `LEARNING.md` during an active session, lit-critic marks findings as potentially stale and recommends a re-run.

- lit-critic **does not auto-rerun** on save.
- The stale prompt is shown **once per analysis snapshot** (to avoid repetitive nagging).
- The Discussion Panel shows a stale-context banner with:
  - **Re-run Analysis** (recommended)
  - **Dismiss** (hide banner until next prompt cycle)

For changes to extracted knowledge (characters, terms, threads), run **Refresh Knowledge** and then re-analyze.

Use **Review Current Finding** for local scene-line edits (no re-run needed).

---

## Session Management

All your work is **automatically saved** to a SQLite database (`.lit-critic.db`) in your project directory. Every action — accepting a finding, rejecting one, discussing, navigating — is immediately written to the database. There is no manual "save" step. You can close the tool at any time and pick up exactly where you left off.

### Auto-Save

Every mutation is written to the database immediately:
- Accept/reject a finding → saved
- Discuss a finding → saved
- Navigate to next finding → saved
- Skip minor findings → saved

You never need to remember to save.

### Resuming a Session

If an active session exists (a review you started but didn't finish), the tool offers to resume it:

**CLI:**
```bash
python -m cli sessions resume --project ~/novel/
```

**Web UI:**
The Web UI detects active sessions automatically and offers to resume.
If the saved scene path is no longer valid (for example after moving your
project to another machine), it prompts you for the corrected scene path and
retries resume automatically.

**VS Code:**
Command Palette → `lit-critic: Resume Session`

If the saved scene path is no longer valid, the extension prompts for a corrected
path and retries resume, including auto-resume on startup and from the Sessions
tree "View Session" flow.

### Session Validation

When resuming, the tool validates that:
- Scene file path matches
- Scene content hasn't changed (SHA-256 hash check)

If validation fails (scene was edited since the session began), you can abandon the old session and start fresh.

If the scene file was moved (instead of edited), provide the new path when
prompted and the active session record is relinked to the new location.

### Session History

You can view all past sessions (active, completed, abandoned):

**CLI:**
```bash
python -m cli sessions list --project ~/novel/
python -m cli sessions show 3 --project ~/novel/    # Show session #3 details
python -m cli sessions delete 3 --project ~/novel/  # Delete session #3
```

**Web UI:**
Navigate to http://localhost:8000/sessions — a dedicated page shows all sessions grouped by status, with options to view details and delete.

**VS Code:**
The **Sessions** sidebar tree view (in the lit-critic Activity Bar) shows all sessions grouped by status. Right-click to view details or delete.

### Learning Management

You can view and manage your learning data across all interfaces:

**CLI:**
```bash
python -m cli learning list --project ~/novel/      # List learning data
python -m cli learning export --project ~/novel/    # Export to LEARNING.md
```

**Web UI:**
Navigate to http://localhost:8000/learning — view all learned preferences, export to LEARNING.md, delete individual entries, or reset all learning data.

**VS Code:**
The **Learning** sidebar tree view shows entries by category. Right-click entries to delete them. Use Command Palette for export and reset.

### Important: Ignore Database Files in Git

Add to your `.gitignore`:
```
.lit-critic.db
```

The database contains your review history—don't commit it.

---

## Scene Change Detection

If you edit a scene file during a review, the tool automatically:

1. **Detects the change** rehashes the scene before each finding
2. **Adjusts line numbers** uses difflib to map old lines to new lines
3. **Marks stale findings** findings in edited regions are flagged
4. **Re-evaluates stale findings** sends them back to the AI for update or withdrawal

This works in all three interfaces. No opt-in required.

### CLI Example

```
📝 Scene change detected!
   Adjusted: 3 findings, Stale: 1 finding
   Re-evaluated: Finding #5 → updated (lines shifted)
```

### VS Code

Scene changes trigger automatic re-evaluation. The Discussion Panel shows notifications for adjusted and re-evaluated findings.

### Web UI

Scene change notifications appear in the chat thread.

---

## Analysis Modes and Slots

Use modes to control depth and cost profile:

| Mode | What runs | Typical cost profile |
|------|-----------|----------------------|
| **quick** | Full analysis with quick checker tier | Lower |
| **deep** | Full analysis with deep checker + frontier tier | Highest |

Use slot configuration to choose exact models per tier:

- `quick` slot: checker model for quick mode
- `deep` slot: checker model for deep mode
- `frontier` slot: discussion/frontier model used where applicable

Recommended baseline:

```bash
python -m cli config set frontier=sonnet deep=sonnet quick=haiku
```

---

## The Horizon Lens

The **Horizon lens** is a seventh lens that works differently from the other six.
It does **not** diagnose problems. Instead it surfaces **unexplored artistic possibilities** —
narrative strategies, structural patterns, voice registers, or craft techniques that
the scene *systematically avoids*.

### Purpose

Where the other six lenses ask *"What's wrong here?"*, the Horizon lens asks
*"What roads are not being taken?"* This is grounded in research showing that
users who received unbiased samples (rather than samples from within their
existing hypothesis space) discovered new possibilities 5× more often than those
who didn't.

### What it examines

- **Narrative strategies not employed** — unreliable narration, time jumps, in-medias-res, epistolary fragments, shifting POV
- **Structural patterns absent** — parallel structure, frame narratives, montage, scene-within-scene
- **Voice registers unused** — if prose is consistently lyrical, where could dryness serve? If spare, where could lushness?
- **Dialogue techniques not attempted** — overlapping speech, silence as dialogue, dialect, indirect speech
- **Sensory channels underused** — if visual dominates, what role could sound, smell, texture, proprioception play?
- **Emotional range unexplored** — if tone is consistently tense, where could levity, absurdity, or tenderness create contrast?

### Output format

Horizon findings use a different schema from standard findings:

| Field | Meaning |
|-------|---------|
| `category` | `opportunity` / `pattern` / `comfort-zone` |
| `observation` | What is absent and why it matters (specific to this scene) |
| `possibility` | A description of how the unexplored technique could work here (not a rewrite) |
| `literary_example` | A published work where the technique is used effectively |

**`opportunity`** — a specific technique that could enrich this particular scene  
**`pattern`** — a recurring absence across the author's style (inferred from STYLE.md / LEARNING.md)  
**`comfort-zone`** — an observation about the author's systematic avoidance of an entire craft dimension

### Inverted learning

Where the other lenses suppress findings that match learned preferences, the
Horizon lens does the **opposite**: if LEARNING.md shows you've repeatedly
declined suggestions in a certain direction, the Horizon lens treats that as a
*pattern observation worth noting*, not a reason for silence.

### Opting out

The Horizon lens respects lens weight preferences. Set `horizon: 0.0` to disable it:

Use the API weight override: `{"weights": {"horizon": 0.0}}`

### Discussion

Horizon findings are fully discussable. The discussion prompt knows this is an
artistic observation, not a problem to defend — the critic explores possibilities,
offers examples, and acknowledges deliberate choices without pressure.

---

## Learning System

The tool tracks your preferences and saves them to the project database. You can export them to `LEARNING.md` as a human-readable file.

### What Gets Learned

- **Rejections** Patterns you consistently reject
- **Acceptances** Feedback you consistently accept
- **Ambiguity answers** Intentional vs. accidental choices
- **Discussion outcomes** Explicit preferences from conversations

### Saving Learning

**CLI:**
```
Type: export learning
```

**Web UI:**
```
Click: Save Learning button
```

**VS Code:**
```
Command Palette → lit-critic: Export Learning to LEARNING.md
```

This writes (or updates) `LEARNING.md` in your project root.

### How It's Used

Future reviews load `LEARNING.md` and all lenses are instructed to respect your documented preferences. The tool calibrates to your style over time.

See **[Learning System Guide](learning-system.md)** for details.

---

## Streaming Discussion

Discussion responses stream token-by-token for faster perceived response.

- **CLI** tokens appear incrementally in the terminal
- **Web UI** tokens stream via Server-Sent Events
- **VS Code** tokens stream in the Discussion Panel

All interfaces fall back gracefully on error.

---

## Cost Management

### Estimate Costs

Typical 3–4 page scene:
- **quick**: lower-cost full analysis
- **deep**: fuller analysis depth and typically highest cost

The API surfaces `mode_cost_hint` and `tier_cost_summary` in analysis responses.
Use these to compare expected mode-level cost impact for your current slot configuration.

The Horizon lens adds one extra API call per analysis. You can disable it by
setting `{"weights": {"horizon": 0.0}}` in your lens preferences to reduce
costs back to 9 calls (6 lenses + 3 coordinator chunks).

Discussion adds extra cost per message (usually $0.01–0.05 per turn).

### Reduce Costs

1. **Run `knowledge refresh`** before iterating to validate scene chain and extract knowledge
2. **Skip minor findings** (`skip minor`) to end reviews faster
3. **Use `--mode quick`** for regular drafting passes
4. **Reserve `--mode deep`** for high-confidence review and polish

---

## Comparison

| Feature | CLI | Web UI | VS Code |
|---------|-----|--------|---------|
| **Interface** | Terminal | Browser | Editor |
| **Speed** | Fast | Fast | Fast |
| **Visuals** | Text-only | Styled UI | Squiggles + panel |
| **Navigation** | Keyboard | Mouse + keyboard | Both |
| **Inline annotations** | No | No | Yes (diagnostics) |
| **Session save/resume** | ✅ | ✅ | ✅ |
| **Learning** | ✅ | ✅ | ✅ |
| **Scene change detection** | ✅ | ✅ | ✅ |
| **Streaming** | ✅ | ✅ | ✅ |
| **Portability** | Any terminal | Any browser | VS Code only |

All three use the same Platform-managed workflow and SQLite project database—use whichever fits your workflow.

---

## Tips

### Keyboard Shortcuts

- **CLI**: Just press Enter to advance through findings quickly
- **Web UI**: Click focus stays in the chat input—type and press Enter
- **VS Code**: Use `Ctrl+Shift+]` to jump to next finding

### Focus on High-Severity First

Type `skip minor` to focus on critical and major findings. You can review minor ones later if you have time.

### Auto-Save Has You Covered

All your progress is automatically saved to the database. If the tool crashes or you close it, you won't lose anything — just resume where you left off.

### Edit While Reviewing

Don't be afraid to edit your scene during a review. Scene change detection will adjust line numbers and re-evaluate affected findings.

### Use Discussion to Challenge

If a finding doesn't make sense, discuss it. The AI can revise, withdraw, or explain better. You're not stuck with the initial assessment.

---

## See Also

- **[Getting Started](getting-started.md)** Initial setup
- **[Working with Findings](working-with-findings.md)** Accept, reject, discuss
- **[Learning System](learning-system.md)** How preferences are tracked
- **[Scene Format](scene-format.md)** @@META documentation
- **[Knowledge Management Guide](index-files.md)** CANON.md, STYLE.md, and auto-extracted knowledge
