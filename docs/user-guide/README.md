# User Guide

Welcome. This guide covers everything you need to use lit-critic as a novelist — from first installation to working with your project over many writing sessions.

---

## What lit-critic is

An AI editorial assistant for novel writers. It reads your scenes and checks them against the rules you've established — your world's logic (CANON.md), your prose conventions (STYLE.md), and knowledge extracted automatically from your prose (characters, terms, threads, timeline).

It presents its observations as **findings**, each tied to a specific passage in your scene. You review them and decide: accept, reject, or debate. The tool never writes prose for you or rewrites your sentences.

---

## Start here

**New to lit-critic?**

1. → **[Setting Up Your Project](setting-up-your-project.md)** — installation, project folder, CANON.md, STYLE.md, scene files
2. → **[Your First Review](your-first-review.md)** — walk through a real analysis session in VS Code, Web, or CLI

**Ready to go deeper?**

3. → **[Understanding Findings](understanding-findings.md)** — what findings contain, how to respond effectively
4. → **[Knowledge and Continuity](knowledge-and-continuity.md)** — how the tool tracks your world automatically
5. → **[The Learning System](learning-system.md)** — how it adapts to your style over time
6. → **[Why This Isn't Sycophantic](sycophancy.md)** — why the tool argues back, and why that matters

**Practical questions?**

→ **[Tips and FAQ](tips-and-faq.md)** — choosing an interface, cost, saving, multi-scene sessions, troubleshooting

---

## The seven lenses

lit-critic analyzes each scene through seven editorial perspectives:

| Lens | What it checks |
|------|---------------|
| **Prose** | Rhythm, fluidity, voice consistency |
| **Structure** | Pacing, scene objectives, narrative threads |
| **Logic** | Character motivation, cause-and-effect, world consistency |
| **Clarity** | Reference resolution, grounding, legibility |
| **Continuity** | Facts, terms, timeline coherence |
| **Dialogue** | Character voice, register, subtext, turn dynamics |
| **Horizon** | Artistic possibilities the scene systematically avoids |

All seven run in parallel. A typical scene takes 30–90 seconds.

---

## Your project files

| File | Purpose | Who maintains it |
|------|---------|-----------------|
| `CANON.md` | World rules and invariants | You |
| `STYLE.md` | Prose conventions | You |
| Scene files | Your prose, with minimal `@@META` headers | You |
| Characters, terms, threads, timeline | Extracted knowledge | Automatic |

The tool extracts characters, terms, narrative threads, and timeline entries automatically from your prose — you don't maintain separate files for them.

---

## Documentation map

```
docs/user-guide/
├── README.md                        ← You are here
├── setting-up-your-project.md       ← Start here if you're new
├── your-first-review.md             ← Step-by-step walkthrough
├── understanding-findings.md        ← What findings are, how to respond
├── knowledge-and-continuity.md      ← CANON.md, STYLE.md, auto-extracted knowledge
├── learning-system.md               ← How the tool adapts to your style
├── sycophancy.md                    ← Why the tool argues back
├── tips-and-faq.md                  ← Practical guidance and common questions
└── templates/
    ├── scene-template.txt           ← Annotated scene file starter
    ├── CANON-template.md            ← World rules starter
    └── STYLE-template.md            ← Prose conventions starter
```

---

## Technical documentation

Architecture, API reference, installation for developers, testing, versioning, and release workflow are in **[docs/technical/](../technical/)**.
