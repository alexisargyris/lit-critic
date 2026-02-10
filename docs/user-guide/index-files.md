# Index Files Guide

Your lit-critic project includes six **index files** (sometimes called "documents of record"). These files live in your project's root directory and serve as the canonical maps for continuity, world rules, and navigation.

Think of them as your novel's reference library—the source of truth when you need to check a fact, verify a term, or track a narrative thread.

---

## Overview

| File | Purpose | Update When |
|------|---------|-------------|
| **TIMELINE.md** | Scene sequence with brief outcomes | Every new or changed scene |
| **CANON.md** | World rules and invariants | When rules or constraints change |
| **CAST.md** | Character facts and relationships | When character details change |
| **GLOSSARY.md** | Controlled vocabulary with first-seen IDs | When new terms appear |
| **THREADS.md** | Open narrative promises and their status | When threads open or close |
| **STYLE.md** | Prose micro-rules (tense, punctuation, etc.) | When you establish new style rules |

---

## 1. TIMELINE.md

**Purpose:** The reading-order sequence of your novel with one or two lines summarizing each scene's outcome.

**Why it matters:** When you revise scene 42, you need to know what happened in scenes 40–43 without re-reading them. TIMELINE.md gives you that at a glance.

### Structure

```markdown
# Timeline

## Part 01 — The Awakening

### Chapter 01

**01.01.01** Amelia wakes in the sanctuary. Discovers her hematocrit is 28%. George is missing.

**01.01.02** Amelia searches the upper sanctum. Finds George's notes about the vault.

**01.01.03** Amelia descends to the vault level. The Breach Gates are sealed but the corridor smells wrong.

### Chapter 02

**01.02.01** Flashback: Three days earlier, Amelia and George argue about opening the vault.

...
```

### Guidelines

- **One line per scene** (two if the scene is complex)
- **Focus on outcomes**, not process (what changed, not how)
- **Include key facts** (numbers, states) if they're important for continuity
- **Use chronological markers** if the narrative is non-linear (e.g., "Flashback: Day -3")

### When to Update

- **After writing a new scene** add the outcome immediately
- **After major revisions** if the scene's outcome changed, update the summary
- **When rearranging scenes** reorder the entries to match reading order

---

## 2. CANON.md

**Purpose:** The immutable rules of your fictional world. Physical laws, magic systems, social constraints, technological limits—anything that characters cannot violate without breaking the world's logic.

**Why it matters:** When Amelia drinks the potion in scene 5, you need to know if that breaks the "no magic inside sanctuaries" rule you established in scene 2. CANON.md is the authoritative answer.

### Structure

```markdown
# Canon

## World Rules

### Physical Laws
- Gravity is 1.2x Earth standard
- Atmosphere is breathable but thin (equivalent to 3000m altitude on Earth)
- Days are 27 standard hours

### Magic System
- Magic requires blood contact with runestones
- Sanctuaries block all magic within their wards
- Ward strength degrades 5% per day without maintenance

### Biological Constraints
- Hematocrit below 25% causes loss of consciousness
- Humans cannot survive more than 3 days without water
- Healing magic does not work on infections

## Historical Constraints
- The war ended 12 years ago (current year = 842 Post-Armistice)
- The old capital was destroyed; no survivors
- Breach Gates were sealed 200 years ago

## Social Rules
- Sanctuary law supersedes kingdom law within ward boundaries
- Blood oaths are binding (magical enforcement)
- Speaking the Forbidden Tongue is punishable by exile
```

### Guidelines

- **Record rules when they first matter** in a scene
- **Be specific**: "Magic is limited" is vague. "Magic requires blood contact with runestones" is actionable.
- **Distinguish cannot from will-not**: CANON.md is for "cannot" (physical impossibility). Character choices ("George will not betray Amelia") go elsewhere.
- **Update immediately** when you revise a world rule, then search your scenes to ensure consistency

### When to Update

- **When you introduce a new rule** that constrains future scenes
- **When you change an existing rule** (search all scenes for the old rule and revise)
- **When a scene references a rule** you haven't documented yet

---

## 3. CAST.md

**Purpose:** Character facts, relationships, and histories. The source of truth for names, ages, physical traits, backstories, and how characters relate to one another.

**Why it matters:** In scene 15, you wrote "Amelia was twelve when the war ended." In scene 47, you need to know her current age. CAST.md has the math.

### Structure

```markdown
# Cast

## Main Characters

### Amelia Ashvale
- **Age:** 24 (born Year 818 PA)
- **Role:** Sanctuary warden, former soldier
- **Physical:** 168cm, lean build, burn scar on right forearm, brown eyes
- **Key facts:**
  - Fought in the final year of the war (age 12)
  - Trained by George since age 13
  - Only surviving member of her squad
- **Relationships:**
  - George: mentor, father-figure, trusts implicitly
  - Lyra: sister-in-arms, complicated loyalty
  - High Priest: mutual distrust

### George Thorne
- **Age:** 56 (born Year 786 PA)
- **Role:** Sanctuary elder, former battle-mage
- **Physical:** 182cm, gray hair, missing left index finger
- **Key facts:**
  - Lost his magic during the war (has not revealed how)
  - Holds the only key to the vault
  - Diagnosed with bloodrot (terminal, 6 months)
- **Relationships:**
  - Amelia: protégé, sees her as a daughter
  - Lyra: former rival, grudging respect
  - High Priest: old friend, growing tension

## Supporting Characters

### Lyra Voss
- **Age:** 27
- **Role:** Scout, information broker
- **Physical:** 175cm, red hair, no visible scars
- **Relationships:**
  - Amelia: complicated (past betrayal forgiven but not forgotten)
  - George: distrusts him

...
```

### Guidelines

- **Include measurements** when they matter (age, height, time-since-event)
- **Track relationships bidirectionally** (both "Amelia trusts George" and "George sees Amelia as a daughter")
- **Note secrets** if they're character-defining (e.g., "George hides his terminal diagnosis")
- **Update facts immediately** when you reveal or change them in a scene

### When to Update

- **When you introduce a new character** (even minor ones, if they'll recur)
- **When you reveal a new fact** about a character
- **When relationships shift** (e.g., Amelia learns of George's betrayal)

---

## 4. GLOSSARY.md

**Purpose:** Controlled vocabulary for specialized terms, place names, invented words, and non-English terms. Ensures consistent spelling and usage throughout the novel.

**Why it matters:** If you spell it "Breach Gates" in scene 3 and "breach gates" in scene 9 and "Breachgates" in scene 15, searching for consistency breaks. GLOSSARY.md is the official spelling.

### Structure

```markdown
# Glossary

## Terms

### Breach Gates
**Definition:** The ancient sealed portals leading to the underworld. Locked 200 years ago after the First Incursion.  
**First seen:** 01.01.03  
**Notes:** Always capitalized. Plural form even when referring to a single gate.

### hematocrit
**Definition:** Percentage of blood volume composed of red blood cells. Normal human range: 38–50%. Below 25% is life-threatening.  
**First seen:** 01.01.01  
**Notes:** Lowercase. Used as both noun and adjective ("hematocrit level" or just "hematocrit").

### sanctuary ward
**Definition:** Magical barrier protecting sanctuary grounds. Blocks all magic, including healing spells.  
**First seen:** 01.01.02  
**Notes:** Lowercase unless starting a sentence. Strength measured in percentage (100% = full strength).

### Κυρία (Kyria)
**Definition:** Greek term meaning "Lady" or "Mistress." Used as a title of respect for the High Priestess.  
**First seen:** 01.02.03  
**Transliteration:** Kyria  
**Notes:** Always capitalize. The Greek spelling is canonical; use transliteration in prose only when POV character doesn't know Greek.

## Place Names

### The Ashvale Sanctuary
**Definition:** Fortified monastery on the eastern ridge. One of twelve sanctuaries remaining after the war.  
**First seen:** 01.01.01  
**Notes:** "The" is part of the official name.

...
```

### Guidelines

- **Record the first scene ID** where each term appears
- **Note capitalization, hyphenation, spacing** explicitly
- **Include transliterations** for non-English terms
- **Provide context** (definition, usage notes)

### When to Update

- **Immediately when you introduce a new term** in a scene
- **When you standardize spelling** of an existing term (then search-and-replace across all scenes)
- **When you realize you've been inconsistent** (pick the official version, record it, fix all scenes)

---

## 5. THREADS.md

**Purpose:** Track narrative promises—questions raised, mysteries introduced, arcs begun—and their current status.

**Why it matters:** In scene 8, you hinted that George is hiding something. In scene 40, you need to know if you've resolved that thread or if it's still hanging.

### Structure

```markdown
# Threads

## Active Threads

### vault_mystery
**Opened:** 01.01.02  
**Question:** What's inside the vault? Why did George hide the key?  
**Status:** Active. Amelia found the vault door ajar (01.03.01) but hasn't entered yet.  
**Notes:** Reader knows George is dying; Amelia doesn't. This asymmetry is intentional.

### George_secret
**Opened:** 01.02.01  
**Question:** Why did George lose his magic? What happened during the war?  
**Status:** Active. Mentioned in flashback but not explained.  
**Notes:** Plan to resolve in Part 02, Chapter 04.

### ward_collapse
**Opened:** 01.01.02  
**Question:** Why are the sanctuary wards failing? Who's sabotaging them?  
**Status:** Active. Clues planted in 01.02.03 (ward strength dropping faster than decay rate).  
**Notes:** Connected to vault_mystery.

## Resolved Threads

### Amelia_injury
**Opened:** 01.01.01  
**Closed:** 01.04.05  
**Resolution:** Amelia received transfusion from Lyra; hematocrit restored to 34%.  
**Notes:** Physical arc resolved but emotional aftermath (Amelia owes Lyra a debt) remains active.

...
```

### Guidelines

- **Give each thread a short ID** (e.g., `vault_mystery`) for easy reference in scene @@META headers
- **Record the scene ID where the thread opened**
- **Update status regularly** as you write
- **Move to "Resolved"** when the question is answered or the arc completes

### When to Update

- **When you open a new thread** (introduce a question or promise)
- **When you advance a thread** (provide new clues or complications)
- **When you resolve a thread** (answer the question, complete the arc)

---

## 6. STYLE.md

**Purpose:** Your novel's prose micro-rules—tense conventions, punctuation preferences, sentence structure habits, term usage guidelines.

**Why it matters:** You wrote scene 1–10 with "Amelia said" as the default dialogue tag. In scene 11, you start using "Amelia spoke." STYLE.md is where you decide the rule and stick to it.

### Structure

```markdown
# Style Guide

## Tense Rules

### Default Tense
Past tense for present-time narrative.

### Flashbacks
Use present tense for flashbacks (inverted convention).  
Example: "Three days earlier, Amelia *stands* in the vault corridor..."

## Dialogue Tags

### Default Tag
Use "said" as the default neutral tag. Avoid fancy tags ("exclaimed," "retorted") unless the manner of speech is essential.

### Tag Placement
Place tags after the first clause of multi-sentence dialogue:  
✅ "I don't know," Amelia said. "The vault was already open."  
❌ Amelia said, "I don't know. The vault was already open."

## Terminology

### Magic System Terms
- "ward" (lowercase) unless starting a sentence
- "Breach Gates" (always capitalized, always plural)
- "runestone" (one word, lowercase)

### Greek Terms
Use Greek spelling (e.g., Κυρία) in narration when POV character knows Greek. Use transliteration (e.g., Kyria) when POV character doesn't.

## Punctuation

### Em Dashes
Use em dashes (—) for abrupt interruptions or shifts in thought. No spaces around the dash:  
✅ "Amelia, I—"  
❌ "Amelia, I —"

### Oxford Comma
Always use the Oxford comma in lists:  
✅ "Amelia, George, and Lyra"  
❌ "Amelia, George and Lyra"

## Sentence Structure

### Sentence Length
Vary sentence length to control pacing. Action scenes: shorter sentences. Introspective scenes: longer, more complex syntax.

### Filter Words
Avoid unnecessary filter words ("saw," "felt," "heard") in deep POV:  
❌ Amelia *saw* the door ajar.  
✅ The door hung ajar.

...
```

### Guidelines

- **Document the rule, not every instance** (you don't need to list every dialogue tag, just the policy)
- **Include examples** (show the right way and the wrong way)
- **Distinguish rules from preferences** (rules = never break; preferences = default unless there's a reason)
- **Update when you catch yourself inconsistently** (if you notice you've been inconsistent, pick the rule, record it, and search-fix)

### When to Update

- **When you establish a new stylistic convention** (e.g., you decide flashbacks use present tense)
- **When you catch an inconsistency** and pick the official way
- **When you deliberately break a rule** (note the exception and why)

---

## How lit-critic Uses These Files

When you run an analysis on a scene, lit-critic loads all six index files to provide context:

- **TIMELINE.md** Checks if the scene's Prev/Next pointers match the reading order
- **CANON.md** Flags violations of world rules (e.g., Amelia uses magic inside the sanctuary)
- **CAST.md** Catches character inconsistencies (e.g., George's age doesn't match his backstory)
- **GLOSSARY.md** Detects term spelling variations (e.g., "breach gates" vs. "Breach Gates")
- **THREADS.md** Warns if you're advancing a thread marked as resolved, or if threads go stale
- **STYLE.md** Highlights deviations from your documented prose rules

The tool respects your world and your voice—it's checking for internal consistency, not imposing external standards.

---

## Best Practices

### 1. Update As You Write
Don't wait until the end of a chapter to update index files. When you introduce a term, add it to GLOSSARY.md immediately. When you close a thread, move it to "Resolved" in THREADS.md.

### 2. Use Index Files While Drafting
Before writing a scene, skim the relevant index files. About to write a scene with George? Check CAST.md for his age, traits, and relationships. About to reference the vault? Check CANON.md for the rules.

### 3. Search for Consistency
When you update a fact (e.g., change George's age from 54 to 56), search your entire project for the old value and fix all scenes.

### 4. One Source of Truth
If a fact appears in multiple index files (e.g., George's terminal diagnosis is in both CAST.md and a THREADS.md entry), make sure they agree. Better yet, put the fact in one place and cross-reference it.

---

## See Also

- **[Scene Format Guide](scene-format.md)** How to structure scene files with @@META headers
- **[Getting Started](getting-started.md)** Project setup walkthrough
- **[Templates](templates/)** Annotated template files for all index documents
- **[Working with Findings](working-with-findings.md)** Understanding lit-critic's feedback
