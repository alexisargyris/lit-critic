# Using the Tool

lit-critic offers three interfaces for reviewing your scenes. Choose the one that fits your workflow.

---

## CLI (Command Line Interface)

The terminal-based interface. Fast, keyboard-driven, and scriptable.

### Basic Usage

```bash
python lit-critic.py analyze --scene path/to/scene.txt --project path/to/project/
```

### Model Selection

Choose which model to use:

```bash
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --model opus        # Claude: Deepest
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --model sonnet      # Claude: Default
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --model haiku       # Claude: Fastest
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --model gpt-4o      # OpenAI: Balanced
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --model gpt-4o-mini # OpenAI: Fast & cheap
```

CLI analysis is single-scene per run. For consecutive multi-scene analysis in one session, use the Web UI or VS Code extension selector.

### Lens Preset (`--lens-preset`)

The CLI now defaults to `--lens-preset auto`.

- `auto` resolves to `single-scene` in CLI analyze runs (CLI currently analyzes one scene per run)
- You can still manually override with `balanced`, `prose-first`, `story-logic`, or `clarity-pass`

Examples:

```bash
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --lens-preset auto
python lit-critic.py analyze --scene scene.txt --project ~/novel/ --lens-preset story-logic
```

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

- **Setup screen** Select scene file(s), project directory, model, and lens preset (`Auto` recommended)
- **Multi-scene analysis** Use "Add another scene" to select consecutive scenes for cross-boundary analysis
- **Live progress** Watch each lens complete in real-time
- **Chat interface** Discuss findings naturally
- **Action buttons** Accept, Reject, Next, Skip Minor
- **Source scene badges** In multi-scene sessions, each finding shows which scene it belongs to
- **Session persistence** Your model choice and paths are remembered

### Workflow

1. **Select files** on the setup screen (use "Add another scene" for consecutive multi-scene analysis)
2. **Choose model** (Claude: Opus/Sonnet/Haiku, or OpenAI: GPT-4o/GPT-4o-mini)
3. **Choose lens preset** (`Auto` is the default and resolves to `single-scene` or `multi-scene` based on selected scene count; other presets are manual overrides)
4. **Start analysis** progress bars show each lens
5. **Review findings** one at a time — source scene is shown for multi-scene sessions
6. **Save learning** to capture your preferences

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

4. **(Optional) Set lens preset behavior**
   - Setting: `literaryCritic.lensPreset`
   - Default: `auto` (recommended)
   - With `auto`, the extension resolves preset at analysis time:
     - one selected scene → `single-scene`
     - multiple selected scenes → `multi-scene`
   - Other preset values act as manual overrides

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
| Analyze Current Scene | `Ctrl+Shift+L` | Start new analysis |
| Re-run Analysis with Updated Indexes | — | Re-run after CANON/CAST/GLOSSARY/STYLE/THREADS/TIMELINE/LEARNING changes |
| Resume Session | — | Continue saved session |
| Next Finding | `Ctrl+Shift+]` | Skip to next |
| Accept Finding | — | Accept current finding |
| Reject Finding | — | Reject with reason |
| Review Current Finding | — | Re-check finding against scene edits |
| Skip Minor | — | Skip minor findings |
| Clear Session | — | Delete saved session |
| Export Learning to LEARNING.md | — | Export LEARNING.md |
| Select Model | — | Choose your model |
| Stop Server | — | Stop the local API process |

### Interoperability

The extension shares the same SQLite database (`.lit-critic.db`) with the CLI and Web UI. Start a review in one interface, close it, and resume in another — everything is automatically saved.

### Index context changes and re-run recommendation

If you edit index context files during an active session (`CANON.md`, `CAST.md`, `GLOSSARY.md`, `STYLE.md`, `THREADS.md`, `TIMELINE.md`, or `LEARNING.md`), lit-critic marks findings as potentially stale and recommends a full re-run.

- lit-critic **does not auto-rerun** on save.
- The stale prompt is shown **once per analysis snapshot** (to avoid repetitive nagging).
- The Discussion Panel shows a stale-context banner with:
  - **Re-run Analysis** (recommended)
  - **Dismiss** (hide banner until next prompt cycle)
- You can also run the Command Palette action: **lit-critic: Re-run Analysis with Updated Indexes**.

Use this rerun when project context changed globally. Keep using **Review Current Finding** for local scene-line edits.

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
python lit-critic.py resume --project ~/novel/
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
python lit-critic.py sessions list --project ~/novel/
python lit-critic.py sessions view 3 --project ~/novel/    # View session #3 details
python lit-critic.py sessions delete 3 --project ~/novel/  # Delete session #3
```

**Web UI:**
Navigate to http://localhost:8000/sessions — a dedicated page shows all sessions grouped by status, with options to view details and delete.

**VS Code:**
The **Sessions** sidebar tree view (in the lit-critic Activity Bar) shows all sessions grouped by status. Right-click to view details or delete.

### Learning Management

You can view and manage your learning data across all interfaces:

**CLI:**
```bash
python lit-critic.py learning view --project ~/novel/      # View learning data
python lit-critic.py learning export --project ~/novel/     # Export to LEARNING.md
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

## Model Selection

Choose a model based on your needs:

| Model | Provider | Speed | Quality | Cost per Scene |
|-------|----------|-------|---------|----------------|
| **Haiku** | Claude | Fastest | Good | $0.02–0.05 |
| **Sonnet** | Claude | Balanced | Excellent | $0.10–0.15 |
| **Opus** | Claude | Slowest | Best | $0.50–0.75 |
| **GPT-4o** | OpenAI | Balanced | Excellent | ~$0.10–0.15 |
| **GPT-4o-mini** | OpenAI | Very Fast | Good | ~$0.02–0.05 |

**Default:** Sonnet (best balance for most users)

### When to Use Each

- **Haiku / GPT-4o-mini** Quick drafts, early revisions, tight budget
- **Sonnet / GPT-4o** Normal use, balanced quality/speed
- **Opus** Final polish, complex scenes, maximum depth

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
- **7 API calls** (6 lenses + coordinator)
- **Sonnet**: ~$0.10–0.15
- **Opus**: ~$0.50–0.75
- **Haiku**: ~$0.02–0.05

Discussion adds extra cost per message (usually $0.01–0.05 per turn).

### Reduce Costs

1. **Use Haiku or GPT-4o-mini** for early drafts
2. **Skip minor findings** (`skip minor`) to end reviews faster
3. **Use Sonnet or GPT-4o** for normal work (good balance)
4. **Save Opus** for final polish

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
- **[Index Files](index-files.md)** CANON, CAST, etc.
