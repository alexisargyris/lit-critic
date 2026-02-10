# Using the Tool

lit-critic offers three interfaces for reviewing your scenes. Choose the one that fits your workflow.

---

## CLI (Command Line Interface)

The terminal-based interface. Fast, keyboard-driven, and scriptable.

### Basic Usage

```bash
python lit-critic.py --scene path/to/scene.txt --project path/to/project/
```

### Model Selection

Choose which model to use:

```bash
python lit-critic.py --scene scene.txt --project ~/novel/ --model opus        # Claude: Deepest
python lit-critic.py --scene scene.txt --project ~/novel/ --model sonnet      # Claude: Default
python lit-critic.py --scene scene.txt --project ~/novel/ --model haiku       # Claude: Fastest
python lit-critic.py --scene scene.txt --project ~/novel/ --model gpt-4o      # OpenAI: Balanced
python lit-critic.py --scene scene.txt --project ~/novel/ --model gpt-4o-mini # OpenAI: Fast & cheap
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
| `save session` | Save progress |
| `clear session` | Delete saved session |
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

- **Setup screen** Select scene file, project directory, and model
- **Live progress** Watch each lens complete in real-time
- **Chat interface** Discuss findings naturally
- **Action buttons** Accept, Reject, Next, Skip Minor
- **Session persistence** Your model choice and paths are remembered

### Workflow

1. **Select files** on the setup screen
2. **Choose model** (Claude: Opus/Sonnet/Haiku, or OpenAI: GPT-4o/GPT-4o-mini)
3. **Start analysis** progress bars show each lens
4. **Review findings** one at a time
5. **Save session** to resume later
6. **Save learning** to capture your preferences

---

## VS Code Extension

Native editor integration with squiggly underlines, sidebar tree, and discussion panel.

### Installation

```bash
cd vscode-extension
npm install
npm run package
code --install-extension lit-critic-0.2.0.vsix --force
```

Or press **F5** in the `vscode-extension` folder for development mode.

### Setup

1. **Open your novel project** in VS Code (the folder with `CANON.md`)
2. **Set repo path** (if your novel is outside the lit-critic installation):
   - Open Settings (`Ctrl+,`)
   - Search for `literaryCritic.repoPath`
   - Set to the absolute path of the lit-critic directory

### Usage

1. **Open a scene file** (`.txt` in your `text/` folder)
2. **Press `Ctrl+Shift+L`** (or Command Palette → "lit-critic: Analyze Current Scene")
3. **Wait for analysis** (status bar shows progress)
4. **Review findings** in the Discussion Panel

### Features

#### Squiggly Underlines
Findings appear as diagnostics in the editor:
- **Red** (Error) — Critical severity
- **Yellow** (Warning) — Major severity
- **Blue** (Info) — Minor severity

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
| Resume Session | — | Continue saved session |
| Next Finding | `Ctrl+Shift+]` | Skip to next |
| Accept Finding | — | Accept current finding |
| Reject Finding | — | Reject with reason |
| Skip Minor | — | Skip minor findings |
| Save Session | — | Save progress |
| Clear Session | — | Delete saved session |
| Save Learning | — | Write LEARNING.md |
| Select Model | — | Choose your model |
| Stop Server | — | Stop backend |

### Interoperability

The extension shares session files (`.lit-critic-session.json`) and `LEARNING.md` with the CLI and Web UI. Start in one interface, save, and resume in another.

---

## Session Management

All three interfaces support session save/resume.

### Saving a Session

**CLI:**
```
Type: save session
(or type 'quit' and answer 'y' when prompted)
```

**Web UI:**
```
Click: Save Session button
```

**VS Code:**
```
Command Palette → lit-critic: Save Session
```

Session is saved to `.lit-critic-session.json` in your project directory.

### Resuming a Session

**CLI:**
```bash
python lit-critic.py --resume --project ~/novel/
```

**Web UI:**
```
The Web UI detects saved sessions automatically and offers to resume
```

**VS Code:**
```
Command Palette → lit-critic: Resume Session
```

### Session Validation

The tool validates that:
- Scene file path matches
- Scene content hasn't changed (hash check)

If validation fails, start a fresh review.

### Clearing a Session

**CLI:**
```
Type: clear session
```

**Web UI:**
```
Click: Clear Session button
```

**VS Code:**
```
Command Palette → lit-critic: Clear Session
```

Or manually delete `.lit-critic-session.json` from your project.

### Important: Ignore Session Files in Git

Add to your `.gitignore`:
```
.lit-critic-session.json
```

Session files are temporary review state—don't commit them.

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

The tool tracks your preferences and saves them to `LEARNING.md`.

### What Gets Learned

- **Rejections** Patterns you consistently reject
- **Acceptances** Feedback you consistently accept
- **Ambiguity answers** Intentional vs. accidental choices
- **Discussion outcomes** Explicit preferences from conversations

### Saving Learning

**CLI:**
```
Type: save learning
```

**Web UI:**
```
Click: Save Learning button
```

**VS Code:**
```
Command Palette → lit-critic: Save Learning
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
- **6 API calls** (5 lenses + coordinator)
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

All three share the same backend and session files—use whichever fits your workflow.

---

## Tips

### Keyboard Shortcuts

- **CLI**: Just press Enter to advance through findings quickly
- **Web UI**: Click focus stays in the chat input—type and press Enter
- **VS Code**: Use `Ctrl+Shift+]` to jump to next finding

### Focus on High-Severity First

Type `skip minor` to focus on critical and major findings. You can review minor ones later if you have time.

### Save Often

Use `save session` periodically, especially for long scenes. If something crashes, you won't lose progress.

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
