# lit-critic

> **PERSONAL PROJECT NOTICE**  
> This is a personal tool that I maintain for my own novel-writing workflow. It was developed with the assistance of claude-opus-4-6 and I'm sharing it publicly in case it's useful to others, but please note:
> - **No support provided** Use at your own risk
> - **Not accepting contributions** I implement features as I need them
> - **Issues/PRs may be ignored** I fix what affects me
> - **Active development** I continue to work on this for my personal use
> - **Fork and adapt** Feel free to fork and adapt it to your needs under the MIT License

**A multi-lens editorial review system for fiction manuscripts.**

lit-critic (short for Literary Critic) reads your novel scenes and provides detailed feedback through five analytical "lenses"—Prose, Structure, Logic, Clarity, and Continuity. The tool doesn't generate your content or impose external standards; it checks your work against **your own rules** as defined in your project's index files.

---

## 📚 For Novel Authors

You're writing a novel and want AI-powered editorial feedback that respects your voice and world-building.

### Quick Start

1. **[Getting Started Guide](docs/user-guide/getting-started.md)** Install and set up your first project
2. **[Scene Format Guide](docs/user-guide/scene-format.md)** How to structure scene files with @@META headers
3. **[Index Files Guide](docs/user-guide/index-files.md)** Maintain CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE
4. **[Using the Tool](docs/user-guide/using-the-tool.md)** CLI, Web UI, and VS Code Extension
5. **[Working with Findings](docs/user-guide/working-with-findings.md)** Understand and respond to feedback
6. **[Learning System](docs/user-guide/learning-system.md)** How the tool adapts to your style

### Templates

Get started quickly with annotated templates:
- **[Scene Template](docs/user-guide/templates/scene-template.txt)** Complete @@META header with inline comments
- **[Index File Templates](docs/user-guide/templates/)** CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE

### Three Ways to Use lit-critic

| Interface | Best For | Quick Start |
|-----------|----------|-------------|
| **CLI** | Keyboard-driven workflow | `python lit-critic.py --scene scene.txt --project ~/novel/` |
| **Web UI** | Visual interface | `python lit-critic-web.py` → http://localhost:8000 |
| **VS Code Extension** | Native editor integration | See [VS Code setup](docs/user-guide/using-the-tool.md#vs-code-extension) |

### Cost Estimate

- **Sonnet** (default): ~$0.10–0.15 per scene
- **Opus**: ~$0.50–0.75 per scene (deepest analysis)
- **Haiku**: ~$0.02–0.05 per scene (fastest)

---

## 🔧 For Developers

You want to integrate lit-critic into your tools or understand its architecture.

### Quick Links

- **Installation**: See [Installation Guide](docs/technical/installation.md) for developer setup
- **Testing**: Run `npm test` (runs both Python and TypeScript tests) — See [Testing Guide](docs/technical/testing.md)
- **Architecture**: System design and data flow — See [Architecture Guide](docs/technical/architecture.md)
- **API Reference**: Complete REST API documentation — See [API Reference](docs/technical/api-reference.md)

### Project Structure

```
lit-critic/
├── cli/                    # CLI interface
├── server/                 # FastAPI backend (shared by all interfaces)
├── web/                    # Web UI
├── vscode-extension/       # VS Code extension
├── tests/                  # Test suites
└── docs/
    ├── user-guide/         # Non-technical documentation
    └── technical/          # Developer documentation
```

### Running Tests

```bash
# All tests (Python + TypeScript)
npm test

# Python tests only
pytest

# TypeScript tests only
npm run test:ts

# With coverage
pytest --cov=server --cov=cli --cov=web
```

### Development

```bash
# CLI
python lit-critic.py --scene scene.txt --project ~/novel/

# Web UI (with auto-reload)
python lit-critic-web.py --reload

# VS Code Extension (F5 launch)
cd vscode-extension && code . 
# Press F5 to launch Extension Development Host
```

---

## How It Works

1. **Loads** your index files (CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE) and scene
2. **Runs 5 lenses in parallel**:
   - **Prose** Fluidity, rhythm, voice consistency
   - **Structure** Pacing, scene objectives, narrative threads
   - **Logic** Character motivation, cause-effect, world consistency
   - **Clarity** Reference clarity, grounding, legibility
   - **Continuity** Term consistency, fact tracking, timeline coherence
3. **Coordinates** results: deduplicates, prioritizes, detects conflicts
4. **Presents** findings one at a time with line-number locations
5. **Discusses** findings with you—the AI can revise, withdraw, or defend based on your input
6. **Learns** your preferences and saves them to LEARNING.md for future sessions

---

## Philosophy: Editor, Not Ghostwriter

**lit-critic is designed as an editorial assistant, not a content generator.**

In an era flooded with AI-generated content, lit-critic takes a fundamentally different approach:

### What lit-critic Does

✅ **Analyzes your work** Reviews your scenes for internal consistency  
✅ **Validates against YOUR rules** Checks CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE  
✅ **Identifies issues** Points out logic gaps, continuity errors, unclear passages  
✅ **Provides conceptual guidance** Suggests approaches like "Consider breaking into two sentences"  
✅ **Respects your voice** Never attempts to rewrite your prose

### What lit-critic Does NOT Do

❌ **Write scenes for you** Never generates prose, paragraphs, or dialogue  
❌ **Rewrite your work** Never offers complete sentence rewrites  
❌ **Impose external standards** Only checks against rules YOU define  
❌ **Generate AI content** Maximum suggestion: 2-3 example words to illustrate a concept

### Example: Minimal Suggestions

When lit-critic suggests specific wording (rarely), it's minimal:

**Not this:** "Consider rephrasing to: 'Amelia stepped into the sanctuary, her footsteps echoing through the vaulted chamber as ancient symbols glowed faintly on the walls.'"

**But this:** "The entrance is described twice in quick succession. Consider consolidating or varying the description."

Or at most: "Consider varying—perhaps 'entered' or 'crossed the threshold.'"

### Your Novel, Your Voice

- **You remain the author** Every word of prose is yours
- **Your world, your rules** Tool validates consistency with your definitions
- **Discussion, not dictation** Findings can be debated, revised, or withdrawn
- **Human creativity preserved** Tool amplifies your craft, doesn't replace it

This philosophy is embedded in every design decision—from how findings are presented to how the discussion system responds. lit-critic exists to help you write **your** novel better, not to write it for you.

---

## Key Features

### For Authors

✅ **Five Editorial Lenses** Prose, Structure, Logic, Clarity, Continuity  
✅ **Three Interfaces** CLI, Web UI, VS Code Extension (all share the same backend)  
✅ **Interactive Discussion** Debate findings with your chosen AI, which can revise or withdraw  
✅ **Learning System** Adapts to your style over time via LEARNING.md  
✅ **Session Resume** Save progress and continue later  
✅ **Scene Change Detection** Edit mid-review; line numbers adjust automatically  
✅ **Your Rules, Your Voice** Checks against CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE

### For Developers

✅ **FastAPI Backend** REST API shared by all interfaces  
✅ **Comprehensive Tests** Python (pytest) and TypeScript (mocha)  
✅ **Streaming Responses** Token-by-token discussion via SSE  
✅ **Structured Output** LLM tool use for reliable parsing  
✅ **Interoperable Sessions** Same session files work across CLI, Web UI, and VS Code  
✅ **Line-Number Tracking** Findings include precise line ranges for editor integration

---

## Multilingual Support

**Your novel can be in any language supported by your chosen AI model.**

lit-critic provides a unique combination: **English-language feedback** on **multilingual prose**.

### How It Works

- **Interface language:** English (findings, discussion, all UI text)
- **Scene text language:** 100+ languages depending on model choice
- **Index files:** Can be in your novel's language (CANON, CAST, GLOSSARY, etc.)

### Why English Feedback?

lit-critic provides feedback in English (not your novel's language) for a pragmatic reason: modern AI models may comprehend adequately 100+ languages but their ability to write editorial feedback in these languages is more variable. English output ensures:

- **Consistent quality** Reliable, nuanced feedback regardless of your novel's language
- **Full editorial vocabulary** Complex editorial concepts expressed clearly
- **Universal tool** One interface language that most developers and power users can work with

This isn't a limitation—it's leveraging the strengths of modern AI to provide the best possible editorial experience for international authors.

### Example

You write your fantasy novel in Greek. lit-critic analyzes the Greek prose and provides English feedback:

> **Finding #3** (Continuity): The character's hematocrit value is 28% in this scene but was 32% in scene 01.01.01. Check ContAnchors for consistency.

No translation needed—the tool analyzes your Greek text natively and communicates findings in English.

---

## Requirements

- **Python 3.10+**
- **At least one API key:**
  - **Anthropic API key** for Claude models (set as `ANTHROPIC_API_KEY` environment variable)
  - **OpenAI API key** for GPT models (set as `OPENAI_API_KEY` environment variable)
- **Node.js 16+** (for VS Code extension only)

---

## Installation

```bash
# Clone the repository
git clone https://github.com/alexisargyris/lit-critic.git
cd lit-critic

# Install Python dependencies
pip install -r requirements.txt

# Set your API key (choose one or both)
export ANTHROPIC_API_KEY="your-key-here"  # macOS/Linux (Claude models)
setx ANTHROPIC_API_KEY "your-key-here"     # Windows (Claude models)

export OPENAI_API_KEY="your-key-here"     # macOS/Linux (OpenAI models)
setx OPENAI_API_KEY "your-key-here"        # Windows (OpenAI models)
```

See **[Getting Started](docs/user-guide/getting-started.md)** for detailed setup instructions.

---

## Project Setup (Authors)

Create your novel project with this structure:

```
my-novel/
├── CANON.md      # World rules and invariants
├── CAST.md       # Character facts and relationships
├── GLOSSARY.md   # Controlled vocabulary
├── STYLE.md      # Prose rules
├── THREADS.md    # Narrative promises
├── TIMELINE.md   # Scene sequence
└── text/
    └── 01.01.01_scene.txt   # Scene files with @@META headers
```

Use the **[templates](docs/user-guide/templates/)** to get started quickly.

---

## Example Usage

### CLI

```bash
python lit-critic.py \
  --scene ~/my-novel/text/01.03.01_vault.txt \
  --project ~/my-novel/ \
  --model sonnet
```

### Web UI

```bash
python lit-critic-web.py
# Open http://localhost:8000 in your browser
```

### VS Code Extension

1. Open your novel project in VS Code
2. Press `Ctrl+Shift+L` (or Command Palette → "Analyze Current Scene")
3. Review findings in the Discussion Panel

---

## Documentation

### For Authors
- **[Getting Started](docs/user-guide/getting-started.md)** Setup walkthrough
- **[Scene Format](docs/user-guide/scene-format.md)** @@META header documentation
- **[Index Files](docs/user-guide/index-files.md)** CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE
- **[Using the Tool](docs/user-guide/using-the-tool.md)** CLI, Web UI, VS Code
- **[Working with Findings](docs/user-guide/working-with-findings.md)** Accept, reject, discuss
- **[Learning System](docs/user-guide/learning-system.md)** Adaptation to your style
- **[Templates](docs/user-guide/templates/)** Starter files

### For Developers
- **[Architecture Guide](docs/technical/architecture.md)** System design with visual diagram
- **[API Reference](docs/technical/api-reference.md)** Complete REST API documentation
- **[Installation Guide](docs/technical/installation.md)** Developer setup instructions
- **[Testing Guide](docs/technical/testing.md)** Running and writing tests

---

## Interoperability

All three interfaces (CLI, Web UI, VS Code) share:
- **Same backend** (FastAPI REST API)
- **Same session files** (`.lit-critic-session.json`)
- **Same learning files** (`LEARNING.md`)

Start a review in one interface, save the session, and resume in another.

---

## License

MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Alexis Argyris

---

## Support

This is a personal project without formal support. However:
- **Documentation**: See the [User Guide](docs/user-guide/) and [Technical Documentation](docs/technical/)
- **Best approach**: Fork the repository and adapt it to your needs

---

## Roadmap

This roadmap reflects **personal priorities** based on my novel-writing needs. Features will be implemented as I need them for my own work.

### Potential Future Features
- Configurable lenses (enable/disable per session)
- Cross-scene analysis for arc-level structure
- Custom lens definitions
- Batch mode (multiple scenes in sequence)
- Confidence tracking for learned preferences
- Git integration (auto-commit LEARNING.md, tag reviewed scenes)
- MCP server for integration with AI development tools

No timeline or guarantees. See [Future Directions](docs/user-guide/using-the-tool.md#future-directions) in the documentation for more ideas.
