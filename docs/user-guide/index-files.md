# Knowledge Management Guide

Your lit-critic project maintains a **knowledge base** about your novel's world. This knowledge powers continuity analysis — when the tool asks "did Amelia's hematocrit level change unexpectedly?" or "is the vault locked in this scene?", it's drawing on that knowledge base.

There are two kinds of knowledge:

| Kind | Files | How it's maintained |
|------|-------|---------------------|
| **Author-authored** | `CANON.md`, `STYLE.md` | You write and update these by hand |
| **Auto-extracted** | Cast, Glossary, Threads, Timeline | Extracted automatically from your prose |

---

## Author-Authored Knowledge

### CANON.md

The immutable rules of your fictional world: magic systems, physical laws, social constraints, historical constraints, and any "cannot" that characters cannot violate without breaking the world's logic.

**You write CANON.md.** The tool reads it as context during extraction and analysis — it uses CANON.md to avoid generating continuity findings that contradict established world rules.

**Example structure:**

```markdown
# Canon

## Magic System
- Magic requires blood contact with runestones
- Sanctuaries block all magic within their wards
- Ward strength degrades 5% per day without maintenance

## Biological Constraints
- Hematocrit below 25% causes loss of consciousness

## Historical Constraints
- The war ended 12 years ago (current year = 842 Post-Armistice)
```

**When to update CANON.md:**
- When you establish a new world rule in a scene
- When you revise an existing rule (then check your scenes for violations)
- When you want the LLM to treat something as an inviolable constraint

---

### STYLE.md

Your prose micro-rules: tense conventions, punctuation preferences, dialogue tag policy, sentence structure habits, terminology guidelines.

**You write STYLE.md.** The tool reads it during analysis to check for deviations from your documented style.

**Example structure:**

```markdown
# Style Guide

## Tense Rules
Past tense for present-time narrative.
Use present tense for flashbacks (inverted convention).

## Dialogue Tags
Use "said" as the default neutral tag.

## Em Dashes
Use em dashes (—) for abrupt interruptions. No spaces around the dash.
```

**When to update STYLE.md:**
- When you establish a new stylistic convention
- When you catch an inconsistency and pick the official way

---

## Auto-Extracted Knowledge

The following four knowledge categories are extracted automatically from your prose by the LLM during `knowledge refresh`. You do not maintain them by hand. If extraction gets something wrong, correct it with an override rather than editing exported markdown or raw database data.

| Category | What's extracted |
|----------|-----------------|
| **Cast** | Character names, aliases, categories, traits, relationships |
| **Glossary** | Specialized terms, definitions, translations, usage notes |
| **Threads** | Narrative threads opened/advanced/closed, questions raised |
| **Timeline** | Scene-level timeline entries (location, POV, objective, continuity anchors) |

---

## Knowledge Tree Visual States

Each entity in the Knowledge tree displays visual cues based on its current state. Multiple states can apply simultaneously; the highest-priority state determines the icon and color.

| State | Icon | Label | Color | Inline actions | What to do |
|---|---|---|---|---|---|
| Normal | property | — | default | Lock, Delete | No action needed |
| Overridden | property | `overridden` | teal | Reset Override, Lock, Delete | Review; reset if extraction later corrected itself |
| Locked | lock | `locked` | gold | Toggle Lock | Unlock to allow future LLM updates |
| Stale | ⚠ warning | `stale` | red | — | Run **Refresh Knowledge** |
| Flagged | ⚠ warning | `flagged` | orange | Keep ✓, Delete 🗑 | Review and decide — see [Resolving flagged entities](#resolving-flagged-entities) |

**Priority order (highest first):** stale → flagged → locked → overridden

---

## The Knowledge Refresh Command

Run `knowledge refresh` after writing or revising scenes. The command:

1. Refreshes scene chain projections (validates your Prev/Next links)
2. Reports any chain validation warnings (gaps, orphans, cycles)
3. Identifies scenes whose content has changed since the last extraction
4. Sends each changed scene to the LLM (using the `quick` model slot) with CANON.md as context
5. Stores extracted results in the project database

**CLI:**
```bash
lit-critic knowledge refresh --project /path/to/project
```

**VS Code extension:** Click the **Refresh Knowledge** button in the Knowledge view toolbar.

The command is also called automatically when you start a new analysis session.

### Extraction is incremental

Only scenes that have changed since the last refresh are sent for extraction. A scene that hasn't changed does not cost a model call.

### Chain warnings

If your Prev/Next chain has issues (a broken link, an orphaned scene, a cycle), `knowledge refresh` reports them as warnings. Analysis still proceeds — chain issues are advisory, not blocking.

---

## Keeping Knowledge Up To Date (VS Code Extension)

When you edit a scene or a reference file (CANON.md / STYLE.md), the knowledge base becomes out of date. The VS Code extension provides a **staleness-driven workflow** to detect what changed and bring everything back in sync. This workflow is entirely manual — there are no automatic file watchers.

### The full update workflow

#### Step 1 — Edit and save

Edit a scene file or a reference file and save. VS Code marks the file as changed ('M' label with highlight colour in the Source Control view). The knowledge base is now potentially out of date, but the extension does not yet know this.

#### Step 2 — Check for Changes

Click **Check for Changes** in the **Inputs** section header of the Knowledge view.

The extension calls the backend, which compares the current file hashes against the last-known projection hashes. The result is pushed to all three sidebar panels:

- **Inputs panel** — changed file(s) are highlighted in muted red and labelled *stale*.
- **Knowledge panel** — affected knowledge entries are highlighted and labelled *stale*:
  - After a **scene file** change: only entries sourced from that scene are marked stale (characters, terms, threads, timeline entries that were extracted from it).
  - After a **reference file** change (CANON.md or STYLE.md): **all** knowledge entries are marked stale.
- **Sessions panel** — sessions whose stored file hashes differ from the current hashes are highlighted as stale.

A notification shows how many stale inputs were found (e.g. *"1 stale input found"*), or *"Everything is up to date"* if nothing changed.

#### Step 3 — Refresh Knowledge

Click **Refresh Knowledge** in the Knowledge view toolbar.

The system re-extracts knowledge from stale scenes (an LLM call per stale scene, using the `quick` model slot). Entity locking is respected — locked entries are skipped during extraction and reconciliation.

After extraction, the **reconciliation review pass** runs. This is a second LLM pass that reviews all knowledge against the current scene content:
- Updates field values for unlocked entities where the text evidence warrants changes.
- Flags unsupported unlocked entities for deletion. If a flagged entity has user overrides, it is placed in the *review* queue rather than being deleted immediately.

When the operation completes, the extension automatically re-queries staleness. Knowledge entries that were refreshed successfully are no longer marked stale.

**If the reconciliation pass flagged any entities for review**, a notification reports the count (e.g. *"2 knowledge item(s) flagged for review by reconciliation pass."*). Those entries appear in the Knowledge tree with a ⚠ warning icon, an orange `flagged` label, and inline **Keep** and **Delete** buttons.

#### Step 4 — Resolve flagged entities (if any) {#resolving-flagged-entities}

For each entity marked `flagged`, use the inline buttons that appear when you hover over it in the tree:

- **Keep ✓** — prompts you to choose between:
  - **Keep & Lock** — dismisses the flag and locks the entity so the LLM will not update it again.
  - **Keep Only** — dismisses the flag without locking (the entity may be re-evaluated on the next refresh).
- **Delete 🗑** — shows a confirmation prompt, then permanently removes the entity and all its overrides.

After either action the flag is cleared immediately from the tree. The entity returns to its normal state (normal, overridden, or locked, depending on what was chosen).

#### Step 5 — Refresh stale sessions

Sessions marked stale must be re-run individually. Re-run each stale session using the normal **Analyze** flow. After each re-run, the extension automatically re-queries staleness and the session is cleared from the stale list.

#### Step 6 — Confirm completion

Once all stale knowledge entries have been refreshed and all stale sessions have been re-run, the input file's stale badge clears automatically. Run **Check for Changes** again to confirm: *"Everything is up to date."*

> **Note:** The input badge is a summary indicator. It stays stale until **all** its dependent knowledge entries **and** sessions have been refreshed — not just knowledge alone.

---

### Summary table

| Step | Actor | Action | Result |
|------|-------|--------|--------|
| 1 | User | Edits and saves a scene or reference file | File marked changed by VS Code |
| 2 | User | Clicks **Check for Changes** | Stale files, knowledge entries, and sessions highlighted |
| 3 | User | Clicks **Refresh Knowledge** | Stale scenes re-extracted; reconciliation pass runs; staleness re-checked |
| 4 | User | Resolves flagged entities (keep or delete) | Flagged indicators cleared |
| 5 | User | Re-runs each stale session | Session staleness cleared after each re-run |
| 6 | User | Clicks **Check for Changes** | Confirms everything is up to date |

---

## Known Issues

### Character renames are not always detected automatically

When you rename a character in a scene file, **Refresh Knowledge** will re-extract the scene and add or update the entry for the new name. The reconciliation pass now uses per-scene `cast_present` data — each scene summary includes a `Cast:` field listing the characters present — and includes explicit rename-detection instructions. If the old character name no longer appears in any scene's cast list and a plausible replacement name is present, the reconciliation pass will propose removal of the old entity.

A manual check is still recommended as a belt-and-suspenders step:

1. After refreshing knowledge, check the Knowledge tree for the old character name.
2. If it still appears and should not, use **Delete Knowledge Entity** from its context menu.

### CANON.md change forces scene re-extraction

When CANON.md changes, all knowledge entries are correctly flagged as stale. **Refresh Knowledge** now also force-marks all previously-extracted scenes as stale before the extraction pass runs. This means that even if a scene's prose has not changed, it will be re-extracted against the updated canon — ensuring the extraction LLM uses the new world rules as context.

### STYLE.md change only marks sessions as stale

When STYLE.md changes, the staleness system now correctly marks only **sessions** as stale. Knowledge entries (characters, terms, threads, timeline) are left unaffected, because STYLE.md is used during analysis sessions only — it is not passed to the extraction LLM and has no effect on what is extracted.

---

## Reviewing and Correcting Extracted Knowledge

Extraction is reliable but not perfect. The review workflow lets you inspect what was extracted and correct anything that's wrong.

### Viewing extracted knowledge

**CLI:**
```bash
lit-critic knowledge review --project /path/to/project --category characters
```

Available categories: `characters`, `terms`, `threads`, `timeline`

**VS Code extension:** Open the **Knowledge** view in the sidebar. Entries are grouped by category. Use **Refresh Knowledge** to re-extract from scenes and **Review Knowledge** to load the current review tree. Entries with corrections applied are marked as author-corrected and show their overridden fields in the tooltip.

### Correcting an entry

When extracted knowledge is wrong, you submit an **override** rather than editing the extraction directly. Overrides survive re-extraction — if the scene is re-processed, the extraction result updates, but your correction is applied on top.

**CLI:**
```bash
lit-critic knowledge review --project /path/to/project --category characters
# Follow the interactive prompts to select an entity and field, then type the corrected value
```

**VS Code extension:** You have two editing paths:

- **Quick edit (V1):** click a knowledge entity, or use **Edit Knowledge Entry** from its context menu. Then choose the field, type the corrected value, and save. The tree refreshes immediately.
- **Detailed review (V2):** use **Open Knowledge Review Panel** from the entity context menu to compare extracted values and overrides side by side, save/reset individual fields, and move to the next or previous entity.

`CANON.md` and `STYLE.md` remain normal author-authored files. The Knowledge view correction flow applies only to the auto-extracted categories.

### Deleting an override

If the extraction later corrects itself, you can remove your override:

```bash
lit-critic knowledge review --project /path/to/project --category characters
# Select the entity, select the overridden field, choose "Delete override"
```

**VS Code extension:** Use **Reset Knowledge Override** from the entity context menu for the quick path, or reset an individual field from the Knowledge Review panel. After reset, the tree refreshes from server truth.

---

## The Extraction Lock

If a scene is particularly complex or you want to prevent re-extraction (e.g., you've manually reviewed all its knowledge and are satisfied), you can lock it:

```bash
lit-critic scenes lock scene-name.txt --project /path/to/project
```

**VS Code extension:** Right-click a scene → **Lock Scene**.

Locked scenes are skipped during `knowledge refresh`. To unlock:

```bash
lit-critic scenes unlock scene-name.txt --project /path/to/project
```

The lock only affects extraction — the scene still participates in analysis normally.

---

## Exporting Knowledge to Markdown

You can export all extracted knowledge (with overrides applied) to a single markdown file for external review or archiving:

**CLI:**
```bash
lit-critic knowledge export --project /path/to/project
```

**VS Code extension:** The extension currently focuses on browsing and correcting knowledge in place. Use the CLI command for markdown export.

The export is read-only — it does not affect the database. It produces a structured markdown document covering Cast, Glossary, Threads, and Timeline.

---

## How Extracted Knowledge Is Used During Analysis

When you analyze a scene, lit-critic loads:

- **CANON.md** and **STYLE.md** directly from files (author-authored)
- **Cast, Glossary, Threads, Timeline** serialized from the database (auto-extracted, with overrides applied)

This knowledge is packed into the analysis prompt as context, enabling the LLM to check continuity, flag rule violations, and identify thread inconsistencies — the same job that manually-maintained index files used to do.

---

## Project Setup Checklist

When starting a new project:

1. **Create CANON.md** with your world's core rules
2. **Create STYLE.md** with your prose conventions
3. **Write your scenes** with the minimal @@META header (Prev/Next only)
4. **Run `knowledge refresh`** to initialize extraction and validate the scene chain
5. **Review the Knowledge view** and add overrides for any extraction errors
6. **Run analysis** on any scene

---

## Frequently Asked Questions

**Do I need to maintain CAST.md, GLOSSARY.md, THREADS.md, or TIMELINE.md files?**  
No. Those files are no longer used. Their content is now extracted automatically and stored in the database. If you have old versions of those files, the tool will ignore them.

**What if extraction misses something important?**  
Submit an override for the missing field. You can also add information to CANON.md if it's a world rule that should always be in context.

**Can I still write knowledge by hand like the old index files?**  
CANON.md and STYLE.md are always hand-authored. For the other categories, use overrides to correct or supplement what extraction produces. The override system is designed to persist through re-extractions.

**How often should I run `knowledge refresh`?**  
After any writing session where you changed scenes. Extraction is incremental, so it only processes what changed.

---

## See Also

- **[Scene Format Guide](scene-format.md)** The minimal @@META format (Prev/Next only)
- **[Getting Started](getting-started.md)** Project setup walkthrough
- **[Working with Findings](working-with-findings.md)** Understanding the tool's feedback
