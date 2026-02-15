# User Guide

This guide helps you use lit-critic (short for Literary Critic) to review your fiction manuscripts.

lit-critic is designed for authors who may not be technical. These docs explain everything in plain language, with examples from fiction writing.

---

## What lit-critic Is (And Isn't)

**lit-critic is your editorial assistant—not your ghostwriter.**

### What It IS ✅

- **An editorial assistant** that checks your work against YOUR rules (CANON, CAST, STYLE, etc.)
- **A continuity tracker** that catches logic gaps and timeline inconsistencies
- **A discussion partner** for editorial decisions—you can debate, and it can revise or withdraw findings
- **A learning system** that adapts to your style preferences over time

### What It IS NOT ❌

- **NOT a ghostwriter** Never writes scenes, paragraphs, or dialogue for you
- **NOT a content generator** Never offers AI-generated prose as "suggestions"
- **NOT a rewriter** Maximum suggestion: 2-3 example words to illustrate a concept
- **NOT prescriptive** Checks YOUR rules, not external "best practices"

### Example: How Suggestions Work

**What you WON'T see:**
> "Rewrite this paragraph as: 'Amelia stepped into the sanctuary, her footsteps echoing through the vaulted chamber as ancient symbols glowed faintly on the stone walls.'"

**What you WILL see:**
> "The entrance is described in detail twice within three sentences. Consider consolidating or varying the description."
> 
> Or at most: "Consider varying—perhaps 'entered' or 'crossed the threshold.'"

### Bottom Line

**You write your novel. Every word of prose is yours.** lit-critic helps you maintain consistency with the world and rules you've defined. It's an editor, not a co-author.

---

## Start Here

### New to lit-critic?

1. **[Getting Started](getting-started.md)** Install the tool and set up your first project
2. **[Scene Format Guide](scene-format.md)** Learn the @@META header system
3. **[Index Files Guide](index-files.md)** Understand CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE

### Ready to Review?

4. **[Using the Tool](using-the-tool.md)** Choose CLI, Web UI, or VS Code Extension
5. **[Working with Findings](working-with-findings.md)** Accept, reject, or discuss feedback
6. **[Learning System](learning-system.md)** How the tool adapts to your style

---

## Quick Reference

### Scene Files

Every scene needs:
- **File name** with Scene ID: `01.03.01_vault.txt`
- **@@META header** with 17 metadata keys
- **Scene text** after `@@END`

See **[Scene Format Guide](scene-format.md)** and **[scene-template.txt](templates/scene-template.txt)** for details.

### Index Files

Six files track your novel's continuity:

| File | Purpose | Template |
|------|---------|----------|
| **CANON.md** | World rules | [Template](templates/CANON-template.md) |
| **CAST.md** | Characters | [Template](templates/CAST-template.md) |
| **GLOSSARY.md** | Terms | [Template](templates/GLOSSARY-template.md) |
| **STYLE.md** | Prose rules | [Template](templates/STYLE-template.md) |
| **THREADS.md** | Narrative arcs | [Template](templates/THREADS-template.md) |
| **TIMELINE.md** | Scene sequence | [Template](templates/TIMELINE-template.md) |

See **[Index Files Guide](index-files.md)** for complete documentation.

### The Five Lenses

lit-critic analyzes your scenes through five perspectives:

1. **Prose** Fluidity, rhythm, voice consistency
2. **Structure** Pacing, scene objectives, narrative threads
3. **Logic** Character motivation, cause-effect, world consistency
4. **Clarity** Reference clarity, grounding, legibility
5. **Continuity** Term consistency, fact tracking, timeline coherence

---

## Common Questions

### "Do I need to fill out all the index files?"

No! Start with empty files. Add to them as you write. The tool works with incomplete index files, though it gets more helpful as you populate them.

### "What's the most important @@META field?"

**ContAnchors** (Continuity Anchors). This is where you track hard facts—numbers, states, measurements—that must not drift between scenes.

### "Can I edit scenes during a review?"

Yes! The tool detects changes, adjusts line numbers, and re-evaluates affected findings automatically.

### "Do I have to accept every finding?"

No. You can reject or discuss any finding. The tool adapts to your preferences over time via the learning system.

### "Which interface should I use?"

- **CLI** Fast, keyboard-driven, terminal-based
- **Web UI** Visual, mouse-friendly, browser-based
- **VS Code** Native editor integration with squiggly underlines

All three share the same backend and session files. Use whichever fits your workflow.

### "Can I use lit-critic for novels not written in English?"

**Yes!** lit-critic supports 100+ languages depending on your model choice. Your scene text can be in any language supported by your chosen AI model (Greek, Japanese, Spanish, Arabic, Chinese, etc.), and the tool will provide feedback in English.

Your index files (CANON, CAST, GLOSSARY, etc.) can also be in your novel's language. The discussion system works in English, but it understands your non-English prose perfectly.

**Why English feedback?** Capabilities vary by provider. Modern AI models comprehend 100+ languages excellently but produce editorial feedback most reliably in English. You get the best of both: native-level analysis of your Greek/Japanese/Spanish prose plus consistent, high-quality editorial feedback in English.

**Example:** You write in Greek. lit-critic analyzes the Greek text and provides English feedback:
> **Finding #5** (Continuity): The character's age is listed as 24 in CAST.md but the scene describes them as "in her thirties."

No translation needed—the tool works with your language natively.

---

## Documentation Map

```
docs/user-guide/
├── README.md                    # ← You are here
├── getting-started.md           # Setup and first project
├── scene-format.md              # @@META documentation
├── index-files.md               # CANON, CAST, GLOSSARY, etc.
├── using-the-tool.md            # CLI, Web UI, VS Code
├── working-with-findings.md     # Accept, reject, discuss
├── learning-system.md           # Adaptation to your style
└── templates/
    ├── scene-template.txt       # Annotated scene template
    ├── CANON-template.md        # World rules template
    ├── CAST-template.md         # Character tracking template
    ├── GLOSSARY-template.md     # Term tracking template
    ├── STYLE-template.md        # Prose rules template
    ├── THREADS-template.md      # Narrative threads template
    └── TIMELINE-template.md     # Scene sequence template
```

---

## Need Help?

- **Start with**: [Getting Started](getting-started.md)
- **Scene questions**: [Scene Format Guide](scene-format.md)
- **Index questions**: [Index Files Guide](index-files.md)
- **Usage questions**: [Using the Tool](using-the-tool.md)
- **Feedback questions**: [Working with Findings](working-with-findings.md)
- **Learning questions**: [Learning System](learning-system.md)

---

## Tips for Success

1. **Start small** Try one scene with minimal index files
2. **Use templates** Copy and customize the templates in `templates/`
3. **Update as you write** Keep TIMELINE.md and ContAnchors current
4. **Save learning regularly** After every 2–3 scenes, run `save learning`
5. **Trust your instincts** Reject findings that don't fit your vision
6. **Discuss when unsure** Use the discussion feature to explore findings

---

## Workflow Example

### First Scene

1. Create index files (can be empty): CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE
2. Write your first scene with a @@META header
3. Run analysis: `python lit-critic.py --scene text/01.01.01.txt --project ~/novel/`
4. Review findings, discuss unclear ones
5. Save learning: `save learning`
6. Update TIMELINE.md with scene outcome

### Subsequent Scenes

1. Write scene with @@META header
2. Update index files (add new characters to CAST, terms to GLOSSARY, etc.)
3. Run analysis
4. Review findings (tool now knows your preferences from LEARNING.md)
5. Save learning periodically
6. Update TIMELINE.md

---

## Ready to Start?

→ **[Getting Started Guide](getting-started.md)**
