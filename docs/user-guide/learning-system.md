# Learning System

lit-critic learns your preferences over time and adapts to your writing style. This guide explains how the learning system works and how to use it effectively.

---

## Overview

The learning system tracks your editorial preferences through:

1. **Accept/Reject patterns** Types of findings you consistently accept or reject
2. **Discussion outcomes** Explicit preferences you state in conversations
3. **Ambiguity choices** When you mark ambiguity as intentional vs. accidental
4. **Cross-finding context** Arguments you use that apply to similar findings

All learned preferences are stored in the **project database** (`.lit-critic.db`). You can export them to **LEARNING.md** as a human-readable file. The database is the source of truth; `LEARNING.md` is a convenient export for reading and sharing. On first use, any existing `LEARNING.md` is automatically imported into the database.

---

## What Gets Learned

### 1. Rejection Patterns

When you reject findings of a certain type multiple times, the system learns that this isn't an issue for your style.

**Example:**
```markdown
## Prose Preferences

- Author intentionally uses sentence fragments for pacing in 
  action scenes (not an error)
- Author prefers occasional one-sentence paragraphs for emphasis
```

### 2. Acceptance Patterns

When you consistently accept certain types of findings, the system learns these are blind spots or active preferences.

**Example:**
```markdown
## Prose Preferences

- Author actively avoids filter words ("saw," "felt," "heard") 
  in deep POV
- Author accepts findings about overlong sentences (prefers 
  concision)
```

### 3. Ambiguity Preferences

When you mark ambiguity as intentional vs. accidental, the system learns your stylistic choices.

**Example:**
```markdown
## Clarity Preferences

- Author uses deliberate pronoun ambiguity for mystery/suspense
- Author prefers clarity over economy in action sequences
```

### 4. Explicit Preferences

When you state a preference during discussion, the system captures it as a rule.

**Example conversation:**
```
You: "I always use em dashes without spaces. That's my style."

AI: "Understood. I'll note that in your learning profile."
```

**Result in LEARNING.md:**
```markdown
## Style Preferences

- Em dashes without spaces (author's consistent style)
```

---

## How LEARNING.md is Used

### During Analysis

When you start a new review:

1. The tool loads learning data from the project database (`.lit-critic.db`)
2. All five lenses receive the learning content as context
3. Lenses are instructed to respect your documented preferences

**Effect:**
- Fewer findings on issues you've consistently rejected
- More attention to areas you've accepted in the past
- Better calibration to your specific style

### During Discussion

When you discuss a finding:

1. The AI has access to your learning history
2. The AI references past preferences in its reasoning
3. The AI avoids rehashing arguments you've already made

**Example:**
```
Finding: "This sentence fragment seems incomplete."

AI: "I see from your learning profile that you 
intentionally use fragments for pacing. However, this 
particular fragment appears in an introspective scene 
where you've previously preferred complete sentences. 
Is this usage intentional?"
```

---

## Saving and Exporting Learning

Learning data is **automatically saved** to the project database as you accept, reject, and discuss findings. There is no manual save step for the learning data itself.

To **export** a human-readable `LEARNING.md` file:

### CLI

```bash
python lit-critic.py learning export --project ~/novel/
```

### Web UI

Navigate to http://localhost:8000/learning and click **Export to LEARNING.md**.

### VS Code

Command Palette → `lit-critic: Export Learning to LEARNING.md`

### What Happens

- **LEARNING.md is generated** from the database as a human-readable export
- **Format:** Clean, readable markdown organized by category
- Future reviews load learning data from the database (not from LEARNING.md)

---

## Learning Data Structure

Learning data is organized by category in the database. When exported to LEARNING.md, it looks like:

```markdown
# Learning

PROJECT: My Novel
LAST_UPDATED: 2026-02-09
REVIEW_COUNT: 12

## Preferences

- Author uses sentence fragments for pacing in action scenes
- Author prefers "said" as default dialogue tag (avoids fancy tags)
- Author accepts findings about filter words and actively removes them

## Blind Spots

- Author consistently misses filter words in deep POV
- Author tends to repeat location descriptions

## Resolutions

- Author resolved tense-rule findings by documenting convention in STYLE.md

## Ambiguity Patterns

### Intentional

- Author uses deliberate pronoun ambiguity for mystery effect
- Author leaves chapter endings ambiguous by design

### Accidental

- Author sometimes forgets to ground character positions after scene transitions
```

### Managing Learning Data

You can also manage individual entries:

**Web UI:** http://localhost:8000/learning — delete individual entries or reset all learning data.

**VS Code:** The **Learning** sidebar tree view shows entries by category. Right-click to delete entries.

**CLI:**
```bash
python lit-critic.py learning view --project ~/novel/
```

---

## Confidence Levels

The system tracks how many times a preference has been confirmed:

- **1–2 instances** Tentative preference (still learning)
- **3–5 instances** Established preference (moderate confidence)
- **6+ instances** Strong preference (high confidence)

Stronger preferences have more influence on future analyses.

---

## Best Practices

### 1. Start Fresh with Each Project

LEARNING.md is project-specific. Don't copy it between projects—each novel has its own style.

### 2. Export Learning Snapshots Regularly

After every 2–3 scene reviews, run `export learning` to snapshot your preferences into `LEARNING.md`. Don't wait until the end of the project.

### 3. Review LEARNING.md Periodically

Open LEARNING.md and read it. Make sure it accurately reflects your preferences. You can edit it manually if needed.

### 4. Provide Reject Reasons

When rejecting a finding, briefly explain why. This helps the learning system extract meaningful patterns.

**Good reject reason:**
```
"Intentional repetition for emphasis"
```

**Vague reject reason:**
```
"I don't like this"
```

### 5. Be Consistent

If you accept "sentence fragments are errors" in scene 1 and reject it in scene 5, the system gets confused. Be consistent or explain why this case differs.

### 6. Use Discussion to Teach

When discussing a finding, state your preferences explicitly:

**Good:**
```
"I always use present tense for flashbacks. That's my 
established convention."
```

**Vague:**
```
"I think this is fine."
```

---

## Learning Across Sessions

### Session 1: Initial Review

You review your first scene. No LEARNING.md exists yet.

- Findings reflect general editorial standards
- You accept some, reject others
- You export a learning snapshot at the end

### Session 2: Second Scene

You review a second scene. LEARNING.md now exists.

- Lenses read your preferences
- Fewer findings on rejected patterns
- You continue to refine preferences
- You export learning again

### Session 10: Mature Profile

After reviewing 10 scenes, LEARNING.md is comprehensive.

- Lenses are well-calibrated to your style
- Findings are more relevant and targeted
- Review sessions are faster (fewer irrelevant findings)

---

## Limitations

### What Learning Does NOT Do

❌ **Override world rules** CANON.md violations are always flagged, regardless of preferences

❌ **Ignore continuity errors** Factual contradictions are always flagged

❌ **Replace your judgment** You still review every finding and decide

❌ **Work across projects** LEARNING.md is project-specific

### What Learning DOES Do

✅ **Reduce noise** Fewer findings on issues you don't care about

✅ **Improve relevance** More findings on issues you actively address

✅ **Speed up reviews** Less time arguing about style preferences

✅ **Respect your voice** Lenses adapt to your specific style

---

## Editing LEARNING.md Manually

You can edit LEARNING.md directly if needed:

### Adding Preferences

```markdown
## Prose Preferences

- Author uses em dashes without spaces (consistent style)
```

### Removing Preferences

Delete the line or section you no longer want tracked.

### Clarifying Preferences

```markdown
- Author uses sentence fragments for pacing in action scenes 
  (but not in introspective scenes)
```

### Organizing

Feel free to reorganize for clarity—the tool reads the whole file regardless of order.

---

## Sharing LEARNING.md

### With Collaborators

If you're co-writing, LEARNING.md can be shared to align editorial standards:

1. **Commit LEARNING.md to your repo**
2. **Both authors run reviews with the same learning profile**
3. **Periodically merge and reconcile preferences**

### Across Projects

Generally not recommended—each project has its own style. But if you have strong personal preferences (e.g., "always avoid filter words"), you can copy specific sections.

---

## Resetting Learning

To start fresh:

1. **Reset learning data** (Web learning page, VS Code learning command, or CLI `python lit-critic.py learning reset --project <path>`)
2. **Run a new review** to build fresh signals
3. **Export learning** when you want a new `LEARNING.md` snapshot

---

## Advanced: Learning from Discussion

The most powerful learning happens during discussion. When you explain your reasoning, the system extracts general rules.

### Example 1: Style Rule

**Discussion:**
```
You: "I always use semicolons to connect related thoughts. 
That's my preferred style, not a run-on."

AI: "Understood. I'll note that you use semicolons 
deliberately for thematic connection."
```

**Result in LEARNING.md:**
```markdown
- Author uses semicolons to connect thematically related 
  sentences (intentional style)
```

### Example 2: Genre Convention

**Discussion:**
```
You: "In fantasy, it's standard to introduce terms without 
immediate explanation. Readers expect to infer meaning."

AI: "Fair point. I'll adjust my clarity threshold for 
specialized terms in your fantasy setting."
```

**Result in LEARNING.md:**
```markdown
- Author introduces fantasy terms without immediate 
  explanation (genre convention, readers infer)
```

### Example 3: Structural Choice

**Discussion:**
```
You: "I deliberately write short transitional scenes 
without strong objectives. They're palette cleansers 
between intense chapters."

AI: "I see. These scenes serve pacing rather than 
plot advancement. I'll adjust my structure lens."
```

**Result in LEARNING.md:**
```markdown
- Author writes short transitional scenes without explicit 
  objectives for pacing (intentional structure)
```

---

## Decay and Reinforcement

(Note: Decay mechanism is a future enhancement, not currently implemented.)

**Future behavior:**
- Preferences weaken if not reinforced over many sessions
- Preferences strengthen when repeatedly confirmed
- This prevents stale preferences from lingering forever

---

## See Also

- **[Working with Findings](working-with-findings.md)** Accept, reject, discuss
- **[Using the Tool](using-the-tool.md)** CLI, Web UI, VS Code
- **[Getting Started](getting-started.md)** Initial setup
- **[Scene Format](scene-format.md)** @@META documentation
- **[Index Files](index-files.md)** CANON, CAST, etc.
