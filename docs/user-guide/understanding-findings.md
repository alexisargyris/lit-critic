# Understanding Findings

lit-critic presents its analysis as **findings** — concrete, specific observations tied to a particular passage in your scene. This guide explains what a finding contains and how to respond to it effectively.

> **You are the writer. Every word of prose is yours.** The tool never suggests rewriting your sentences, only what to consider. Suggestions are directions, not dictations — at most two or three example words to illustrate a concept.

---

## What a finding looks like

Every finding has the same structure:

**Severity** — how significant the issue is:
- 🔴 **Critical** — likely to confuse or alienate readers
- 🟡 **Major** — noticeable issue that affects the reading experience
- 🔵 **Minor** — subtle issue or potential improvement

**Lens** — which of the seven editorial perspectives flagged it (Prose, Structure, Logic, Clarity, Continuity, Dialogue, or Horizon)

**Location** — the exact line range in your scene (e.g., L042–L045)

**Evidence** — the specific text or pattern that triggered the finding

**Impact** — why this matters to a reader, in concrete terms

**Suggestions** — one or two conceptual directions to consider ("Consider varying the sentence structure" or "Consider clarifying the timeline here with a single phrase") — never a rewrite

### The Horizon lens is different

Horizon findings don't diagnose problems. They surface artistic possibilities the scene systematically avoids — narrative techniques not attempted, voice registers unused, sensory channels underused. They're offered as invitations, not criticisms. You can discuss, accept, or dismiss them like any other finding.

---

## Your four responses

### Accept
You agree with the observation and plan to address it in your revision.

The finding is marked accepted and the squiggly underline (in VS Code) disappears. The pattern is tracked so the learning system can calibrate future reviews.

**When to accept:** the finding identifies something real, even if you're not sure yet how you'll fix it.

### Reject
You disagree — the "issue" is intentional, or you simply don't plan to change it.

You can optionally type a brief reason. This is the most useful thing you can do for the learning system: a specific rejection reason ("intentional repetition for emphasis") teaches the tool more than a silent dismissal.

**When to reject:** the finding misunderstands your intent, contradicts your established style, or flags something you've deliberately chosen.

### Discuss
You open a conversation with the AI about the finding.

Type your response in the discussion area and the AI will reply — examining your argument, asking clarifying questions, or presenting additional evidence. Based on the exchange, it may:

- **Hold its ground** — defend the finding with more specific evidence
- **Concede** — agree that the finding was based on a misreading
- **Revise** — adjust the severity or framing based on your point
- **Withdraw** — retract the finding entirely

The conversation is saved. You can close the session and come back to a discussion mid-thread.

**When to discuss:** you're unsure whether the finding applies, you have a counterargument, or the finding seems to contradict your established style.

### Skip
Move on without acting. The finding stays pending. You can return to it later.

**When to skip:** you want to see the full picture before deciding, or you need time to think about it.

---

## Discussion: what to expect

The AI does not capitulate easily. "I like it this way" will get you a clarifying question or a more specific defence of the finding — not immediate agreement. You need to give it a real argument.

**Example: the AI concedes**
```
You: "Amelia's confusion here is intentional — she doesn't recognize 
the artifact yet. The ambiguity is the point."

AI: "You're right. The ambiguity serves the story at this moment. 
Withdrawing this finding."
```

**Example: the AI holds its ground**
```
You: "This repetition is intentional for emphasis."

AI: "I understand the intent, but the three occurrences within four 
lines may feel heavy-handed even if the first instance is deliberate. 
Is the repetition meant to build across all three, or only the final one?"
```

**Example: the AI revises downward**
```
You: "Readers can infer the timeline from context."

AI: "Fair point — the surrounding paragraphs do ground it. Downgrading 
from Critical to Minor."
```

---

## Common scenarios

### You disagree with the severity

The finding is real, but the severity feels too high for what it is.

→ Discuss it: "This is minor — readers won't lose the thread here." The AI may revise the severity or explain why it graded it higher.

### You agree with the problem but not the suggestion

The issue is real, but you have your own idea for fixing it.

→ Accept the finding. The acceptance acknowledges the problem; you fix it your way.

### The finding misunderstood your context

The AI flagged a continuity issue that isn't actually wrong — it missed something in CANON.md or a previous scene.

→ Discuss it: "The vault is accessible at this point — the ward collapsed at the end of scene 01.02.04." The AI may withdraw the finding or ask you to verify it in CANON.md.

### You're genuinely unsure

You're not sure if the finding applies.

→ Discuss it: "Can you show me where a reader would get confused?" The AI will give a more specific explanation.

---

## Quick reference

| Interface | Accept | Reject | Discuss | Skip |
|-----------|--------|--------|---------|------|
| **VS Code** | Accept Finding button | Reject Finding button | Type in Discussion Panel | Next Finding (`Ctrl+Shift+]`) |
| **Web UI** | Accept button | Reject button | Type in chat | Next button |
| **CLI** | Enter | Type reason + Enter | Type anything | Enter with no input |

Additional CLI commands during review:

| Command | What it does |
|---------|-------------|
| `skip minor` | Skip all remaining minor-severity findings |
| `review` | Re-check current finding after editing the scene |
| `export learning` | Export your preferences to LEARNING.md |
| `quit` | End the session (progress is saved) |

---

## See also

- **[Your First Review](your-first-review.md)** — walkthrough of a full session
- **[The Learning System](learning-system.md)** — how accept/reject patterns adapt future reviews
- **[Why This Isn't Sycophantic](sycophancy.md)** — why the AI pushes back rather than agreeing
- **[Knowledge and Continuity](knowledge-and-continuity.md)** — how the tool checks your world's facts
