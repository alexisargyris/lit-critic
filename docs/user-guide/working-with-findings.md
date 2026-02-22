# Working with Findings

This guide explains how to interpret and respond to findings from lit-critic's five editorial lenses.

---

## Understanding Findings

Each finding represents one concern identified by one of the five lenses. Findings are presented one at a time in priority order.

### Finding Components

Every finding includes:

#### 1. Severity
How impactful the issue is for readers:

- **Critical** 🔴 — Likely to confuse or alienate readers
- **Major** ⚠️ — Noticeable issue that affects reading experience
- **Minor** ℹ️ — Subtle issue or potential improvement

#### 2. Lens
Which editorial perspective flagged it:

- **Prose** Fluidity, rhythm, voice
- **Structure** Pacing, objectives, threads
- **Logic** Motivation, causality, consistency
- **Clarity** Reference resolution, grounding
- **Continuity** Facts, terms, timeline

#### 3. Location
Line range in your scene (e.g., `L042-L045`).

#### 4. Evidence
The specific text or pattern that triggered the finding.

#### 5. Impact
Why this matters for the reader experience.

#### 6. Suggestions (Conceptual Guidance Only)

**Important:** Suggestions are **conceptual approaches**, not prose rewrites.

lit-critic provides strategic guidance like:
- "Consider breaking into two sentences"
- "Consider consolidating these descriptions"
- "Consider clarifying the timeline with a temporal marker"

**What you WON'T see:**
- Complete sentence rewrites
- AI-generated alternative prose
- Paragraph reconstructions

**What you WILL see:**
- Strategic approaches ("Consider splitting this")
- At most, 2-3 example words to illustrate ("perhaps 'entered' or 'crossed'")
- Conceptual options ("vary the verb" not "change 'walked' to 'strode purposefully'")

**You remain the author.** Suggestions tell you *what* to consider, not *how* to write it. Every word of prose remains yours.

---

## Your Response Options

For each finding, you can:

### 1. Accept
You agree with the finding and plan to address it.

**What happens:**
- Finding marked as "accepted"
- Tracked for learning (patterns you accept)
- (VS Code only) Squiggly underline removed

**When to accept:**
- The finding identifies a real problem
- You agree with the impact assessment
- You plan to revise the scene

### 2. Reject
You disagree with the finding or don't plan to change it.

**What happens:**
- Finding marked as "rejected"
- You can provide a reason (optional but helpful for learning)
- Tracked for learning (patterns you reject)
- (VS Code only) Squiggly underline removed

**When to reject:**
- The finding misunderstands your intent
- The "issue" is intentional for effect
- The suggestion conflicts with your style
- You have a specific reason to keep it as-is

### 3. Discuss
Open a conversation with the AI about the finding.

**What happens:**
- You type a message
- The AI responds, considering your argument
- The AI can revise, withdraw, or escalate the finding based on discussion
- Full conversation history is maintained per finding and persisted with the session
- Re-opening the finding (or viewing session history later) restores the same thread

**When to discuss:**
- You're unsure if the finding applies
- You want to understand the impact better
- You have a counterargument
- The finding seems contradictory

### 4. Skip (Continue)
Move to the next finding without acting.

**What happens:**
- Finding remains in "pending" state
- No learning tracked
- (VS Code only) Squiggly underline remains

**When to skip:**
- You want to think about it
- You'll address it later
- You're just surveying all findings first

### 5. Review Current Finding vs Re-run Analysis

These two actions solve different problems:

- **Review Current Finding**: re-checks the *current* finding after you edit scene text.
  - Use this when you've changed wording, line order, or nearby context in the current scene.
  - It updates that finding in-place (or marks it resolved) without starting a full new run.

- **Re-run Analysis with Updated Indexes**: runs a *full analysis* again when index context changes
  (`CANON.md`, `CAST.md`, `GLOSSARY.md`, `STYLE.md`, `THREADS.md`, `TIMELINE.md`, `LEARNING.md`).
  - Use this when the world/context references changed and findings may be stale across the whole set.
  - In VS Code, the Discussion Panel can show a stale-context banner with a **Re-run Analysis** action.

---

## Discussion Outcomes

When you discuss a finding, the AI can:

### Defend
Stand behind the finding with additional evidence or explanation.

**Example:**
```
You: "This repetition is intentional for emphasis."

AI: "I understand the intent, but the three occurrences 
within four lines may feel heavy-handed to readers. Consider 
keeping the first and last for stronger impact."
```

### Concede
Agree that the finding doesn't apply given your explanation.

**Example:**
```
You: "Amelia's confusion here is intentional—she doesn't 
recognize the artifact yet."

AI: "You're right. The ambiguity serves the story. 
I'm withdrawing this finding."
```

### Revise
Update the finding's severity, evidence, or suggestions based on discussion.

**Example:**
```
You: "This isn't critical—readers can infer the timeline."

AI: "Fair point. I'm downgrading this from Critical 
to Minor. The timeline is inferable but could be clearer."
```

### Withdraw
Retract the finding entirely.

**Example:**
```
You: "George's age is 56, not 54. Check CAST.md."

AI: "You're correct—I misread CAST.md. Withdrawing 
this finding."
```

### Escalate
Increase severity when discussion reveals the issue is worse than initially assessed.

**Example:**
```
You: "Why does this matter? It's just one number."

AI: "Because this hematocrit value appears in three 
other scenes. If it's wrong here, the continuity break 
cascades. Escalating to Critical."
```

---

## Special Finding Types

### Ambiguity Findings

When Clarity lens detects unclear references, you can mark them:

- **Intentional** Deliberate ambiguity for effect (mystery, suspense, unreliable narrator)
- **Accidental** Unintended confusion that needs fixing

This helps the learning system understand your intentional choices vs. mistakes.

### Continuity Conflicts

When Continuity lens finds contradictions:

- Check your **ContAnchors** metadata
- Verify against **CANON.md** or **CAST.md**
- If the tool is wrong, explain in discussion
- If you're wrong, accept and fix

### Structure Gaps

When Structure lens finds missing objectives or stale threads:

- Check **THREADS.md** for thread status
- Verify scene's **Objective** in @@META header
- Discuss if the finding misunderstands your structure

---

## Learning from Your Choices

The tool tracks patterns in your accept/reject decisions:

### What Gets Tracked

- **Rejection patterns** Types of findings you consistently reject
- **Acceptance patterns** Types of findings you consistently accept
- **Ambiguity preferences** When you choose intentional vs. accidental
- **Discussion outcomes** Explicit preferences you state

### How It's Used

Run `export learning` (CLI), click **Save Learning** (Web UI), or use Command Palette (VS Code) to write patterns to `LEARNING.md`.

Future reviews load `LEARNING.md` and lenses are instructed to respect your preferences.

**Example LEARNING.md entry:**
```markdown
## Prose Preferences

- Author prefers sentence fragments for pacing in action scenes 
  (not an error)
- Author accepts findings about filter words ("saw", "felt") and 
  actively removes them
```

---

## Tips for Effective Review

### 1. Focus on High-Severity First

Use `skip minor` to prioritize critical and major findings. You can review minor ones later if time permits.

### 2. Don't Accept Everything

The tool is not infallible. If a finding doesn't make sense or misunderstands your intent, reject it or discuss it.

### 3. Provide Reject Reasons

When you reject a finding, briefly explain why. This helps the learning system understand your preferences.

**Good reject reasons:**
- "Intentional repetition for emphasis"
- "This matches my established style in STYLE.md"
- "The ambiguity is deliberate—mystery setup"
- "This contradicts my prose voice"

### 4. Use Discussion to Challenge

If something feels off, discuss it. The AI can explain better, provide examples, or reconsider the finding.

### 5. Trust Your Instincts

You're the author. The tool provides perspective, but you make the final call.

---

## Common Scenarios

### Scenario 1: You Disagree with Severity

**Finding:** Major — "This sentence is 45 words long and difficult to parse."

**Your view:** It's intentional. Complex syntax fits this introspective scene.

**Action:** Discuss it or reject with reason: "Intentional complex syntax for introspection."

---

### Scenario 2: You Agree with Impact but Not the Suggestion

**Finding:** Critical — "Unclear pronoun reference. Suggestion: Rewrite with explicit noun."

**Your view:** The issue is real, but the suggestion is too heavy-handed.

**Action:** Accept the finding (acknowledging the problem), but fix it your own way.

---

### Scenario 3: The Tool Missed Context

**Finding:** Continuity — "Amelia's hematocrit is 28% here but was 32% in previous scene."

**Your view:** She's bleeding—it dropped on purpose.

**Action:** Discuss: "She's injured. The drop is intentional. Check ContAnchors."

The AI may withdraw the finding or suggest making the change more explicit.

---

### Scenario 4: You're Unsure

**Finding:** Clarity — "The temporal sequence is unclear. Readers may not know when this happens."

**Your view:** Not sure if this is a real problem.

**Action:** Discuss: "Can you show me where the confusion would occur?"

The AI can explain or show specific examples that help you decide.

---

## Commands Quick Reference

### CLI

| Command | Action |
|---------|--------|
| **Enter** | Next finding |
| `skip minor` | Skip all minor findings |
| `skip to structure` | Jump to Structure lens |
| `skip to coherence` | Jump to Coherence lens |
| `review` | Re-check current finding against scene edits |
| `quit` | End session |
| `export learning` | Export `LEARNING.md` |
| `intentional` | Mark ambiguity as intentional |
| `accidental` | Mark ambiguity as accidental |
| **Type anything else** | Discuss |

### Web UI

- **Accept button** Accept finding
- **Reject button** Reject (with optional reason)
- **Next button** Skip to next
- **Skip Minor button** Skip all minor
- **Type in chat** Discuss

### VS Code

- **Accept Finding** (Command Palette) — Accept
- **Reject Finding** (Command Palette) — Reject
- **Next Finding** (`Ctrl+Shift+]`) — Skip
- **Review Current Finding** (Command Palette) — Re-check against scene edits
- **Skip Minor** (Command Palette) — Skip all minor
- **Export Learning to LEARNING.md** (Command Palette) — Export learning markdown
- **Type in Discussion Panel** Discuss

---

## Revision Tracking

When the AI revises a finding during discussion, the original version is preserved:

**Revision history includes:**
- Original severity, evidence, impact, suggestions
- New severity, evidence, impact, suggestions
- Timestamp
- Reason for revision

This lets you see how the finding evolved through discussion.

---

## Finding Status

Each finding has a status:

- **Pending** Not yet acted on
- **Accepted** You agreed and will address it
- **Rejected** You disagreed or won't change it
- **Withdrawn** The AI retracted it during discussion
- **Revised** The AI updated the finding during discussion
- **Escalated** Severity increased during discussion

Status is tracked in the project database (`.lit-critic.db`) and affects learning.

---

## Discussion History Persistence

Discussion is stored per finding as an ordered turn history (`You` / `Critic`, plus
system notes when relevant). This history is visible across interfaces:

- **Web active review**: switching findings rehydrates each finding's saved thread
- **Web sessions history**: session detail view shows each finding's discussion thread
- **VS Code discussion panel**: reopening a finding preloads the persisted thread
- **CLI session detail** (`lit-critic sessions view <id> --project <path>`): shows
  per-finding turn counts and the latest turn summary

This means discussion context is no longer ephemeral; it is part of the finding's
long-term review record.

---

## See Also

- **[Using the Tool](using-the-tool.md)** CLI, Web UI, VS Code interfaces
- **[Learning System](learning-system.md)** How preferences are tracked
- **[Scene Format](scene-format.md)** @@META documentation
- **[Index Files](index-files.md)** CANON, CAST, etc.
- **[Getting Started](getting-started.md)** Initial setup
