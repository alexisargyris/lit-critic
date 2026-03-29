# The Learning System

Every time you accept, reject, or discuss a finding, lit-critic learns something about your style. Over time it calibrates: fewer findings on issues you've consistently dismissed, more attention to patterns you've consistently agreed with. A mature learning profile means reviews that are faster and more relevant to your actual work.

Your preferences are stored as part of your project. You can export them to a readable file called `LEARNING.md` at any point.

---

## What gets learned

**Rejection patterns** — When you reject findings of a certain type repeatedly, the tool learns that this isn't something you care to address. It will flag it again only if the evidence is compelling.

**Acceptance patterns** — When you consistently agree with a type of finding, the tool treats it as a recurring blind spot and pays extra attention to it in future scenes.

**Explicit preferences from discussion** — When you explain your reasoning in a conversation, the tool extracts the principle and stores it.

**Example:**

```
You: "I always use semicolons to connect thematically related thoughts. 
That's my style, not a run-on."

AI: "Understood. I'll note that you use semicolons deliberately for 
thematic connection."
```

Later, `LEARNING.md` will contain:
```markdown
- Author uses semicolons to connect thematically related sentences (intentional style)
```

---

## How it influences future reviews

When you start a new review, all seven lenses receive your learning profile as context. The effect is gradual and calibrated:

- The **first time** you reject a pattern, the tool may still flag it — noting your prior rejection — if the evidence in the new scene is strong
- After **two or three rejections** of the same pattern, the tool flags it only when the evidence is compelling, and acknowledges the tension with your preference
- **No preference is permanent immunity.** A strong enough case will still surface even for patterns you've repeatedly dismissed

This means your reviews don't become an echo chamber. The tool becomes quieter about things you've clearly chosen, but never completely silent.

---

## Exporting your preferences

Your preferences are accumulated automatically. To export them as a readable file:

**VS Code:** Command Palette → `lit-critic: Export Learning to LEARNING.md`

**Web UI:** http://localhost:8000/learning → click **Export to LEARNING.md**

**Terminal:** `python -m cli learning export --project ~/my-novel/`

The exported file looks like:
```markdown
# Learning

PROJECT: My Novel
LAST_UPDATED: 2026-03-10
REVIEW_COUNT: 12

## Preferences

- Author uses sentence fragments for pacing in action scenes (intentional)
- Author prefers "said" as default dialogue tag (avoids fancy tags)
- Author accepts findings about filter words and actively removes them

## Blind Spots

- Author consistently misses filter words in deep POV
```

---

## Teaching from discussion

The most powerful learning happens when you explain your thinking in a discussion rather than just accepting or rejecting.

**Genre conventions:**
```
You: "In fantasy, it's standard to introduce terms without immediate 
explanation. Readers expect to infer meaning from context."

AI: "Fair point. I'll adjust my clarity threshold for specialized 
terms in your fantasy setting."
```

**Structural choices:**
```
You: "I deliberately write short transitional scenes without strong 
objectives. They're palette cleansers between intense chapters."

AI: "Understood — these serve pacing rather than plot advancement."
```

The more specific your explanation, the more useful the resulting learning entry.

---

## Best practices

**Provide reject reasons.** "Intentional repetition for emphasis" teaches the tool far more than a silent dismissal.

**Be consistent.** If you accept "sentence fragments are errors" in scene 1 and reject it in scene 5, the tool gets a mixed signal. When a choice genuinely varies by scene type, say so in the discussion.

**Review LEARNING.md occasionally.** Open it and read it. If something no longer reflects your preferences, you can delete entries directly from the Learning view in VS Code, or reset everything and start fresh.

**Each project is separate.** LEARNING.md is specific to one novel. Don't copy it between projects.

---

## Limitations

| What the learning system does NOT do | Why |
|--------------------------------------|-----|
| Override world rules | CANON.md violations are always flagged, regardless of preferences |
| Ignore continuity errors | Factual contradictions are always flagged |
| Replace your judgment | You still review every finding and decide |
| Guarantee silence on dismissed topics | Strong enough evidence will resurface even preferred patterns |

---

## Managing learning data

**Delete individual entries:** VS Code → Learning view → right-click an entry → Delete

**Reset everything:** VS Code → Command Palette → `lit-critic: Reset All Learning Data` (or http://localhost:8000/learning on the Web UI)

---

## See also

- **[Understanding Findings](understanding-findings.md)** — accept, reject, discuss
- **[Your First Review](your-first-review.md)** — when to export your first snapshot
