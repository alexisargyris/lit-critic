# Getting Started with lit-critic

Welcome! This guide will walk you through setting up lit-critic (short for Literary Critic) for your fiction project.

## What is lit-critic?

lit-critic is an editorial review tool that reads your novel scenes and provides detailed feedback through five analytical "lenses":

1. **Prose** Fluidity, rhythm, voice consistency
2. **Structure** Pacing, scene objectives, narrative threads
3. **Logic** Character motivation, cause-effect, world consistency
4. **Clarity** Reference clarity, grounding, legibility
5. **Continuity** Term consistency, fact tracking, timeline coherence

The tool doesn't impose external standards—it checks your work against **your own rules** as defined in your index files.

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

### 2. Create Index Files

In your project root, create these six files:

- **CANON.md** World rules and invariants
- **CAST.md** Character facts and relationships
- **GLOSSARY.md** Controlled vocabulary
- **STYLE.md** Prose rules
- **THREADS.md** Narrative promises
- **TIMELINE.md** Scene sequence

Don't worry if they're empty for now—you'll populate them as you write. See the **[Templates](templates/)** folder for starter files.

### 3. Create the Text Directory

Create a folder for your scene files:

```
my-novel/
├── CANON.md
├── CAST.md
├── GLOSSARY.md
├── STYLE.md
├── THREADS.md
├── TIMELINE.md
└── text/
    └── (your scene files go here)
```

### 4. Write Your First Scene

Create your first scene file in the `text/` folder. Every scene must start with a `@@META` header.

**Example: text/01.01.01_opening.txt**

```
@@META
ID: 01.01.01
Part: 01
Chapter: 01
Scene: 01
Chrono: D0-Morning
POV: Amelia
Tense: Past
Location: Sanctuary / Amelia's quarters
Cast: Amelia (alone)
Objective: Establish Amelia's situation and the sanctuary setting
Threats: None (opening scene)
Secrets: None
ContAnchors: hematocrit=32%; sanctuary_wards=95%
Terms: hematocrit; sanctuary wards
Threads: None (opening scene)
Prev: None
Next: 01.01.02
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
python lit-critic.py --scene path/to/your-novel/text/01.01.01_opening.txt --project path/to/your-novel/
```

**Example (Windows):**
```bash
python lit-critic.py --scene "C:\Users\YourName\my-novel\text\01.01.01_opening.txt" --project "C:\Users\YourName\my-novel\"
```

**Example (macOS/Linux):**
```bash
python lit-critic.py --scene ~/my-novel/text/01.01.01_opening.txt --project ~/my-novel/
```

### What Happens Next

1. **Loading** The tool loads your index files and scene text
2. **Analysis** Five lenses run in parallel (takes 30–90 seconds)
3. **Findings** Results appear one at a time in priority order
4. **Discussion** You can accept, reject, or discuss each finding

### Choosing a Model

By default, lit-critic uses Sonnet (balanced speed and quality). You can choose a different model:

```bash
python lit-critic.py --scene scene.txt --project ~/my-novel/ --model opus        # Claude: Deepest analysis
python lit-critic.py --scene scene.txt --project ~/my-novel/ --model sonnet      # Claude: Default
python lit-critic.py --scene scene.txt --project ~/my-novel/ --model haiku       # Claude: Fastest & cheapest
python lit-critic.py --scene scene.txt --project ~/my-novel/ --model gpt-4o      # OpenAI: Balanced
python lit-critic.py --scene scene.txt --project ~/my-novel/ --model gpt-4o-mini # OpenAI: Fast & cheap
```

---

## Understanding Findings

Each finding includes:

- **Severity** Critical, Major, or Minor
- **Lens** Which lens flagged it (Prose, Structure, Logic, Clarity, Continuity)
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
| `quit` (or `q`) | End the session (you can save and resume later) |

See **[Working with Findings](working-with-findings.md)** for detailed guidance.

---

## Populating Index Files

As you write more scenes, your index files will grow. Here's when to update each one:

### CANON.md
When you establish a world rule that must never be violated.

**Example:**
```markdown
# Canon

## Magic System
- Sanctuaries block all magic within their wards
- Ward strength degrades 5% per day without maintenance
```

### CAST.md
When you introduce a character or reveal new information about them.

**Example:**
```markdown
# Cast

## Main Characters

### Amelia Ashvale
- **Age:** 24
- **Role:** Sanctuary warden
- **Key facts:**
  - Trained by George since age 13
  - Only surviving member of her squad
```

### GLOSSARY.md
When you introduce a specialized term.

**Example:**
```markdown
# Glossary

### hematocrit
**Definition:** Percentage of blood volume composed of red blood cells.  
**First seen:** 01.01.01  
**Notes:** Lowercase. Normal range: 38–50%.
```

### STYLE.md
When you establish a prose convention.

**Example:**
```markdown
# Style Guide

## Tense Rules
Past tense for present-time narrative.  
Present tense for flashbacks (inverted convention).
```

### THREADS.md
When you raise a narrative question or promise.

**Example:**
```markdown
# Threads

## Active Threads

### vault_mystery
**Opened:** 01.02.01  
**Question:** What's inside the vault?  
**Status:** Active
```

### TIMELINE.md
After writing or revising each scene.

**Example:**
```markdown
# Timeline

## Part 01

**01.01.01** Amelia wakes. Hematocrit is 32%. Morning duty begins.  
**01.01.02** Amelia patrols the sanctuary grounds. Notices ward strength declining.
```

See **[Index Files Guide](index-files.md)** for complete documentation.

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

### "Missing index files"
- The tool shows warnings but continues without them
- Create the six index files (even if empty) to get better results

### Analysis takes too long
- Try `--model haiku` for faster analysis
- Typical scene (3–4 pages) takes 30–90 seconds with Sonnet

### Invalid scene format
- Make sure your scene starts with `@@META` and ends with `@@END`
- See **[Scene Format Guide](scene-format.md)** for requirements

---

## Cost Estimate

Each review costs approximately (examples using Anthropic models):

- **Sonnet** (default): $0.10–0.15 per scene (3–4 pages)
- **Opus**: $0.50–0.75 per scene (deepest analysis)
- **Haiku**: $0.02–0.05 per scene (fastest)

Costs depend on scene length and complexity.

---

## See Also

- **[Scene Format Guide](scene-format.md)** Complete @@META documentation
- **[Index Files Guide](index-files.md)** CANON, CAST, GLOSSARY, etc.
- **[Using the Tool](using-the-tool.md)** CLI, Web UI, VS Code Extension
- **[Working with Findings](working-with-findings.md)** Accept, reject, discuss
- **[Learning System](learning-system.md)** How the tool learns your preferences
- **[Templates](templates/)** Starter files for your project
