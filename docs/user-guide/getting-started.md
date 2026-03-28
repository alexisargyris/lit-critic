# Getting Started with lit-critic

Welcome! This guide will walk you through setting up lit-critic (short for Literary Critic) for your fiction project.

## What is lit-critic?

lit-critic is an editorial review tool that reads your novel scenes and provides detailed feedback through seven analytical "lenses":

1. **Prose** Fluidity, rhythm, voice consistency
2. **Structure** Pacing, scene objectives, narrative threads
3. **Logic** Character motivation, cause-effect, world consistency
4. **Clarity** Reference clarity, grounding, legibility
5. **Continuity** Term consistency, fact tracking, timeline coherence
6. **Dialogue** Character voice distinctiveness, register consistency, and conversational dynamics
7. **Horizon** Unexplored artistic possibilities — narrative strategies, structural patterns, voice registers, and craft techniques the scene systematically avoids

The tool doesn't impose external standards—it checks your work against **your own rules** as defined in CANON.md and STYLE.md (which you write) plus knowledge extracted automatically from your prose.

### Language Support

Your novel can be in **any language supported by your chosen AI model**—including Greek, Japanese, Spanish, Arabic, Chinese, and 100+ others. The tool's interface and feedback are in English, but it analyzes your non-English prose natively.

**Example:** You write your novel in Greek with Greek index files. lit-critic analyzes the Greek text and provides English-language findings like:

> **Finding #1** (Prose): The sentence "Η Ελένη περπάτησε..." is 47 words long and may be difficult to parse. Consider breaking into shorter sentences for better rhythm.

Your index files can also be in your novel's language. The tool works seamlessly with multilingual content—no translation needed.

**Why English feedback?** Capabilities vary by provider. Modern AI models read and understand 100+ languages at near-native level but write editorial feedback most reliably in English. This design choice ensures consistent, nuanced feedback regardless of your novel's language.

---

> **🎯 Important: lit-critic is an Editor, Not a Ghostwriter**
>
> lit-critic is designed as an **editorial assistant**, not a content generator. It will never offer to write scenes or paragraphs for you. When it suggests specific wording (rarely), it's only 2-3 words as an example to illustrate a concept.
>
> **You remain the author—every word of prose is yours.** The tool helps you maintain consistency with your own rules, but it doesn't write for you.
>
> This is fundamentally different from AI writing tools that generate content. lit-critic validates and discusses your work; it doesn't create it.

---

## Prerequisites

### 1. Python Installation
lit-critic requires Python 3.10 or newer. Check if you have it:

**Windows:**
```bash
python --version
```

**macOS/Linux:**
```bash
python3 --version
```

If you don't have Python, download it from [python.org](https://www.python.org/downloads/).

### 2. API Key (Choose One or Both)

The tool supports multiple AI providers. You need at least one API key:

**Option A: Anthropic (Claude models)**
Get an API key from [Anthropic](https://www.anthropic.com/).

**Windows (Command Prompt):**
```bash
setx ANTHROPIC_API_KEY "your-key-here"
```

**Windows (PowerShell):**
```bash
$env:ANTHROPIC_API_KEY = "your-key-here"
```

**macOS/Linux:**
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

**Option B: OpenAI (GPT models)**
Get an API key from [OpenAI](https://platform.openai.com/).

**Windows (Command Prompt):**
```bash
setx OPENAI_API_KEY "your-key-here"
```

**Windows (PowerShell):**
```bash
$env:OPENAI_API_KEY = "your-key-here"
```

**macOS/Linux:**
```bash
export OPENAI_API_KEY="your-key-here"
```

Add this to your `.bashrc` or `.zshrc` to make it permanent.

---

## Installation

### 1. Download lit-critic

Clone or download the lit-critic repository to your computer:

```bash
git clone https://github.com/alexisargyris/lit-critic.git
cd lit-critic
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the necessary Python packages.

---

## Project Setup

lit-critic expects your fiction project to follow a specific structure. Let's set it up.

### 1. Create Your Project Directory

Create a folder for your novel (separate from the lit-critic installation):

```
my-novel/
```

### 2. Create Author-Authored Knowledge Files

In your project root, create these two files:

- **CANON.md** World rules and invariants (magic systems, physical laws, constraints)
- **STYLE.md** Prose rules (tense, punctuation, terminology conventions)

Don't worry if they're empty for now—you'll populate them as you write.

> **What about CAST.md, GLOSSARY.md, THREADS.md, TIMELINE.md?**
> These are no longer needed as hand-maintained files. Characters, terms, threads, and timeline entries are extracted automatically from your prose when you run `knowledge refresh`. See the **[Knowledge Management Guide](index-files.md)** for details.

### 3. Create the Text Directory

Create a folder for your scene files:

```
my-novel/
├── CANON.md
├── STYLE.md
└── text/
    └── (your scene files go here)
```

### 4. Write Your First Scene

Create your first scene file in the `text/` folder. The `@@META ... @@END` block only needs `Prev` and `Next` — everything else is extracted automatically.

**Example: text/01.01.01_opening.txt**

```
@@META
Prev: None
Next: 01.01.02_sanctuary_duty.txt
@@END

Amelia woke to the sound of bells. Three chimes, then silence—the morning call for sanctuary duty. She lay still for a moment, watching dust motes spiral in the narrow shaft of sunlight from the east window.

The hematocrit monitor on her nightstand blinked green: 32%. Stable, for now.

She pushed herself upright and reached for her boots.
```

See **[Scene Format Guide](scene-format.md)** for complete documentation on the `@@META` header.

---

## Running Your First Analysis

You can use lit-critic in three ways: **CLI (terminal)**, **Web UI (browser)**, or **VS Code Extension**. Let's try the CLI first.

### CLI Method

Open a terminal, navigate to the lit-critic installation directory, and run:

```bash
python -m cli sessions start --scene path/to/your-novel/text/01.01.01_opening.txt --project path/to/your-novel/ --mode deep
```

**Example (Windows):**
```bash
python -m cli sessions start --scene "C:\Users\YourName\my-novel\text\01.01.01_opening.txt" --project "C:\Users\YourName\my-novel\" --mode deep
```

**Example (macOS/Linux):**
```bash
python -m cli sessions start --scene ~/my-novel/text/01.01.01_opening.txt --project ~/my-novel/ --mode deep
```

For consecutive multi-scene analysis in one session, use the Web UI or VS Code extension scene-set selector.

### What Happens Next

1. **Loading** The tool loads CANON.md, STYLE.md, and auto-extracted knowledge from the project database, plus your scene
2. **Analysis** Seven lenses run in parallel (takes 30–90 seconds)
3. **Findings** Results appear one at a time in priority order
4. **Discussion** You can accept, reject, or discuss each finding

### Choosing an Analysis Mode

Use `--mode` to control depth:

```bash
python -m cli sessions start --scene scene.txt --project ~/my-novel/ --mode quick      # Faster LLM pass, lower cost
python -m cli sessions start --scene scene.txt --project ~/my-novel/ --mode deep       # Default: deepest review
```

You can control which model each mode uses via persistent model slots:

```bash
python -m cli config set frontier=sonnet deep=sonnet quick=haiku
python -m cli config show
```

---

## Understanding Findings

Each finding includes:

- **Severity** Critical, Major, or Minor
- **Lens** Which lens flagged it (Prose, Structure, Logic, Clarity, Continuity, Dialogue, Horizon)
- **Location** Line range in your scene (e.g., L042-L045)
- **Evidence** The specific text or pattern
- **Impact** Why it matters for the reader
- **Suggestions** Concrete options for fixing it

### Responding to Findings

At each finding, you can:

| Command | What It Does |
|---------|-------------|
| **Enter** (or `continue` or `c`) | Move to the next finding |
| **Type anything** | Start a discussion with the AI about this finding |
| `skip minor` | Skip all minor-severity findings |
| `skip to structure` | Jump to Structure lens findings |
| `skip to coherence` | Jump to Coherence lens findings (Logic + Clarity + Continuity + Dialogue) |
| `quit` (or `q`) | End the session (you can save and resume later) |

See **[Working with Findings](working-with-findings.md)** for detailed guidance.

---

## Maintaining Your Knowledge Files

### CANON.md — you write this
Update CANON.md whenever you establish a world rule that must never be violated.

```markdown
# Canon

## Magic System
- Sanctuaries block all magic within their wards
- Ward strength degrades 5% per day without maintenance

## Biological Constraints
- Hematocrit below 25% causes loss of consciousness
```

### STYLE.md — you write this
Update STYLE.md whenever you establish a prose convention.

```markdown
# Style Guide

## Tense Rules
Past tense for present-time narrative.
Present tense for flashbacks (inverted convention).

## Dialogue Tags
Use "said" as the default neutral tag.
```

### Characters, terms, threads, timeline — extracted automatically
After writing or revising scenes, run:

```bash
python -m cli knowledge refresh --project ~/my-novel/
```

The tool extracts characters, terms, narrative threads, and timeline entries from your prose and stores them in the project database. You can then review what was extracted and add corrections via the Knowledge view.

See the **[Knowledge Management Guide](index-files.md)** for the full workflow.

---

## Next Steps

### Explore Other Interfaces

- **[Web UI](using-the-tool.md#web-ui)** Visual interface in your browser
- **[VS Code Extension](using-the-tool.md#vs-code-extension)** Native editor integration with squiggly underlines

### Learn Advanced Features

- **[Session Resume](using-the-tool.md#session-management)** Save your progress and continue later
- **[Learning System](learning-system.md)** How the tool adapts to your style over time
- **[Scene Change Detection](using-the-tool.md#scene-change-detection)** Edit your scene mid-review without breaking the analysis

### Use Templates

Check the **[Templates folder](templates/)** for annotated starter files for all index documents and scene headers.

---

## Troubleshooting

### "No API key provided"
- Make sure you've set the `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` environment variable
- Or pass it directly: `--api-key your-key-here`

### "Missing knowledge files"
- The tool shows warnings but continues without CANON.md and STYLE.md
- Create CANON.md (even if empty) to get better continuity analysis
- Knowledge extraction (characters, terms, threads) runs automatically on first `knowledge refresh`

### Analysis takes too long
- Try `--mode quick` for faster, lower-cost LLM analysis
- Typical scene (3–4 pages) takes ~30–90 seconds in deep mode

### Invalid scene format
- Make sure your metadata block uses `@@META` and `@@END` delimiters correctly
- See **[Scene Format Guide](scene-format.md)** for delimiter conventions and template recommendations

---

## Cost Estimate

Each review cost depends on your selected mode and model-slot assignments:

- **Quick mode**: lower cost, faster turnaround (uses your `quick` slot)
- **Deep mode**: highest depth and typically highest cost (uses your `deep` slot)

Costs depend on scene length and complexity.

---

## See Also

- **[Scene Format Guide](scene-format.md)** Complete @@META documentation
- **[Knowledge Management Guide](index-files.md)** CANON.md, STYLE.md, and auto-extracted knowledge
- **[Using the Tool](using-the-tool.md)** CLI, Web UI, VS Code Extension
- **[Working with Findings](working-with-findings.md)** Accept, reject, discuss
- **[Learning System](learning-system.md)** How the tool learns your preferences
- **[Templates](templates/)** Starter files for your project
