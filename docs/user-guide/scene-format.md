peak # Scene File Format

This guide explains how to structure your scene files so that lit-critic can analyze them effectively.

## Overview

Each scene in your novel is saved as a **separate text file**. Every scene file has two parts:

1. **@@META header** A metadata block at the very top (for tooling and continuity tracking)
2. **Scene text** Your actual prose

The metadata header helps you (and the tool) track continuity, character presence, timeline position, and narrative threads. It's stripped out during final compilation—readers never see it.

---

## Scene File Naming

Scene files must include their **Scene ID** in the filename. The format is flexible, but clarity helps:

### Required Pattern
```
[Scene ID]_[Optional Description].txt
```

### Examples
```
01.01.01_Amelia_awakens.txt
01.02.03_The_marketplace.txt
02.05.01.txt
```

**Scene IDs are stable.** If you rearrange scenes during revision, keep the same ID unless you're deliberately renumbering.

---

## The @@META Header

Every scene file starts with a metadata block:

```
@@META
[17 lines of key-value pairs]
@@END
```

### Delimiters
- **`@@META`** marks the start (must be on its own line)
- **`@@END`** marks the end (must be on its own line)
- Everything between these delimiters is metadata
- Everything after `@@END` is your scene text

---

## Required Keys

All scene files should include these 17 keys in the same order. Consistency makes searching and reviewing easier.

### 1. ID
The unique scene identifier.

**Format:** `Part.Chapter.Scene`

**Example:**
```
ID: 01.03.01
```

---

### 2. Part
Which part of the novel this scene belongs to.

**Example:**
```
Part: 01
```

---

### 3. Chapter
Which chapter within the part.

**Example:**
```
Chapter: 03
```

---

### 4. Scene
Which scene within the chapter.

**Example:**
```
Scene: 01
```

---

### 5. Chrono
**Timeline position** using your project's chronology system.

This lets you track when scenes happen in story-time (not reading-order). Useful for flashbacks, parallel timelines, or non-linear narratives.

**Format:** Whatever system you use (day-time, absolute minutes, stardate, etc.)

**Examples:**
```
Chrono: D0-T083         (Day 0, Time unit 83)
Chrono: D3-Morning
Chrono: Year_842_Spring
```

Record your chronology system in **CANON.md** so it's consistent.

---

### 6. POV
The **point-of-view character** for this scene.

**Examples:**
```
POV: Amelia
POV: Αναστασία             (use your actual character names/transliterations)
POV: Third-omniscient
```

---

### 7. Tense
Narrative tense and any special rules.

**Examples:**
```
Tense: Past
Tense: Present
Tense: Past (present=flashback rule)
```

If you have tense-inversion rules (e.g., present tense indicates a flashback in an otherwise past-tense narrative), note them here and in **STYLE.md**.

---

### 8. Location
Where the scene takes place.

**Format:** Use slashes or hierarchical notation for specificity.

**Examples:**
```
Location: House / Corridor
Location: Marketplace / Spice Quarter
Location: Ship / Engine Room
Location: Forest clearing
```

---

### 9. Cast
Characters present in the scene.

**Format:** Semicolon-separated list. Include off-screen characters if they're relevant (speaking through doors, heard but not seen, etc.).

**Examples:**
```
Cast: Amelia; George; Lyra
Cast: Αναστασία; Καίτη (off-screen)
Cast: Amelia (alone)
```

---

### 10. Objective
What this scene accomplishes narratively.

**Format:** One clause summarizing the scene's purpose.

**Examples:**
```
Objective: Amelia discovers the locked vault
Objective: George confronts Lyra about the betrayal
Objective: Establish the market's sensory chaos before the attack
```

---

### 11. Threats
Active dangers, tensions, or conflicts present in the scene.

**Format:** Semicolon-separated list.

**Examples:**
```
Threats: Starvation; exposure; pursuer 2km behind
Threats: Lyra suspects Amelia's lie; vault timer running
Threats: None (recovery scene)
```

---

### 12. Secrets
Information asymmetries—what characters know that others don't.

**Format:** Semicolon-separated list.

**Examples:**
```
Secrets: Amelia knows George is dying; George hides this from Lyra
Secrets: Reader knows the vault is empty (Amelia doesn't)
Secrets: None
```

---

### 13. ContAnchors
**Continuity anchors—the most important field.**

This is where you record **hard facts** that must not drift:
- Numeric values (distances, counts, times, measurements)
- Binary states (locked/unlocked, alive/dead, leaking/not-leaking)
- Explicit rule invocations

**Why this matters:** Prose is fluid and subjective. Numbers and states are not. If Amelia's hematocrit is 28% in scene 12, it can't be 34% in scene 13 unless something changed it.

**Format:** Semicolon-separated, using stable terms from GLOSSARY.md

**Examples:**
```
ContAnchors: hematocrit=28%; vault_door=locked; 47 minutes until dawn
ContAnchors: Barrier_Gates=sealed; Amelia_injury=bleeding; George_distance=2km
ContAnchors: Rule_3_invoked (no magic inside sanctuary)
```

**Best practice:** Use the same term every time (e.g., always "hematocrit," never "blood count" or "RBC level"). Record canonical terms in **GLOSSARY.md**.

---

### 14. Terms
Specialized vocabulary used in this scene.

**Format:** Semicolon-separated list of terms from GLOSSARY.md

**Examples:**
```
Terms: θύρες Παραβίωσης; αιματοκρίτης; Κυρία
Terms: Breach Gates; hematocrit; sanctuary rules
Terms: None (mundane scene)
```

These should match entries in **GLOSSARY.md**. If you introduce a new term, add it to the glossary.

---

### 15. Threads
Narrative threads touched in this scene.

**Format:** Semicolon-separated thread IDs or short names

**Examples:**
```
Threads: betrayal_arc; vault_mystery; Amelia_injury
Threads: George_secret; sisterhood_conflict
```

These should reference threads listed in **THREADS.md**.

---

### 16. Prev
The Scene ID of the **previous scene in reading order**.

**Examples:**
```
Prev: 01.02.05
Prev: None            (if this is the first scene)
```

---

### 17. Next
The Scene ID of the **next scene in reading order**.

**Examples:**
```
Next: 01.03.02
Next: TBD             (if you haven't written it yet)
```

---

## Complete Example

Here's a full scene file for a fantasy novel:

```
@@META
ID: 01.03.01
Part: 01
Chapter: 03
Scene: 01
Chrono: D0-T083
POV: Amelia
Tense: Past
Location: Sanctuary / Lower Corridor
Cast: Amelia; George (off-screen voice)
Objective: Amelia discovers the vault door is already open
Threats: Sanctuary wards failing; Amelia's wound still bleeding; unknown intruder
Secrets: Amelia suspects George opened the vault; reader knows George is dying
ContAnchors: vault_door=ajar; hematocrit=28%; ward_strength=12%; 47_minutes_to_dawn
Terms: Breach Gates; hematocrit; sanctuary wards
Threads: vault_mystery; George_secret; ward_collapse
Prev: 01.02.05
Next: 01.03.02
@@END

The corridor smelled of rust and old stone. Amelia pressed one hand against the wall, steadying herself as the vertigo came in waves. Forty-seven minutes until dawn. She had to reach the vault before the wards collapsed entirely.

The Breach Gates were still sealed—she'd checked twice. That meant the intruder was already inside.

George's voice echoed from somewhere ahead, too faint to make out words. He was supposed to be in the upper sanctum. Amelia's jaw tightened. If he'd opened the vault without her...

She rounded the corner and stopped.

The vault door hung ajar. Its iron face bore no scorch marks, no pry marks, no sign of forced entry. Someone had simply unlocked it.

"George," she called, her voice flat. No response.

The hematocrit monitor on her wrist pulsed red: 28%. Still dropping. She had maybe two hours before she'd need a transfusion. Less if she had to fight.

Amelia drew her blade and stepped through the doorway.
```

---

## Multilingual Scenes

**lit-critic supports scenes in any language.** Your scene text can be in Greek, Japanese, Spanish, Arabic, or 100+ other languages depending on your chosen model. The tool analyzes your prose in its original language and provides English-language feedback.

### Example: Greek-Language Scene

Here's the same scene in Greek with Greek metadata:

```
@@META
ID: 01.03.01
Part: 01
Chapter: 03
Scene: 01
Chrono: Η0-Χ083
POV: Ελένη
Tense: Παρελθοντικός
Location: Καταφύγιο / Κάτω διάδρομος
Cast: Ελένη; Μιχάλης (φωνή εκτός σκηνής)
Objective: Η Ελένη ανακαλύπτει ότι η πόρτα του θησαυροφυλακίου είναι ήδη ανοιχτή
Threats: Οι προστατευτικοί θόλοι αποτυγχάνουν; το τραύμα της Ελένης αιμορραγεί ακόμα; άγνωστος εισβολέας
Secrets: Η Ελένη υποψιάζεται ότι ο Μιχάλης άνοιξε το θησαυροφυλάκιο; ο αναγνώστης γνωρίζει ότι ο Μιχάλης πεθαίνει
ContAnchors: πόρτα_θησαυροφυλακίου=μισάνοιχτη; αιματοκρίτης=28%; ισχύς_θωράκισης=12%; 47_λεπτά_μέχρι_την_αυγή
Terms: Πύλες Παραβίωσης; αιματοκρίτης; θωράκιση καταφυγίου
Threads: μυστήριο_θησαυροφυλακίου; μυστικό_Μιχάλης; κατάρρευση_θωράκισης
Prev: 01.02.05
Next: 01.03.02
@@END

Ο διάδρομος μύριζε σκουριά και παλιά πέτρα. Η Ελένη πίεσε το ένα χέρι στον τοίχο, σταθεροποιώντας τον εαυτό της καθώς η ζάλη ερχόταν σε κύματα. Σαράντα επτά λεπτά μέχρι την αυγή. Έπρεπε να φτάσει στο θησαυροφυλάκιο πριν καταρρεύσουν οι θόλοι εντελώς.

Οι Πύλες Παραβίωσης ήταν ακόμα σφραγισμένες—είχε ελέγξει δύο φορές. Αυτό σήμαινε ότι ο εισβολέας ήταν ήδη μέσα.

Η φωνή του Μιχάλη αντήχησε από κάπου μπροστά, πολύ αδύναμη για να ξεχωρίσει λέξεις. Υποτίθεται ότι ήταν στο ανώτερο ιερό. Το σαγόνι της Ελένης σφίχτηκε. Αν είχε ανοίξει το θησαυροφυλάκιο χωρίς αυτήν...

Γύρισε τη γωνία και σταμάτησε.

Η πόρτα του θησαυροφυλακίου κρεμόταν μισάνοιχτη. Η σιδερένια της όψη δεν έφερε σημάδια καψίματος, σημάδια μοχλού, κανένα σημάδι βίαιης εισόδου. Κάποιος απλά την είχε ξεκλειδώσει.

«Μιχάλη», φώναξε, η φωνή της επίπεδη. Καμία απάντηση.

Η οθόνη αιματοκρίτη στον καρπό της παλμοί κόκκινη: 28%. Ακόμα έπεφτε. Είχε μάλλον δύο ώρες πριν χρειαζόταν μετάγγιση. Λιγότερο αν έπρεπε να πολεμήσει.

Η Ελένη τράβηξε τη λεπίδα της και πέρασε από την πόρτα.
```

### How It Works

When you run analysis on this Greek scene, lit-critic:

1. **Analyzes the Greek prose** Checks rhythm, clarity, logic in Greek
2. **Provides English feedback** Findings are presented in English
3. **Understands Greek metadata** Reads your Greek index files (CANON, CAST, etc.)

**Example feedback you might receive:**

> **Finding #2** (Continuity): The ContAnchors field shows `αιματοκρίτης=28%` but your CAST.md lists Amelia's baseline hematocrit as 32%. This is a 4-point drop—is this change intentional and explained in the scene?

**Technical Note:** Capabilities vary by provider. Modern AI models' comprehension of non-English languages exceeds their production capability. The tool provides English feedback because current models analyze your Greek/Japanese/Arabic prose at near-native level but produce more reliable, nuanced editorial feedback in English. This ensures consistent quality across all supported languages.

### Language Coverage

- **Claude Opus & Sonnet:** Excellent support for 100+ languages including Greek, Japanese, Chinese, Arabic, Spanish, Russian, and many others
- **Claude Haiku:** Good support for major world languages; may have reduced quality for rare languages
- **OpenAI GPT models:** Excellent support for major world languages

Your index files (CANON, CAST, GLOSSARY, etc.) can also be in your novel's language—the tool works seamlessly with multilingual content.

---

## Best Practices

### 1. Keep Keys Consistent
Use the same 17 keys in the same order across all scenes. This makes text searching (grep, ctrl-F) fast and reliable.

### 2. Use Stable Terminology
If you call something "Breach Gates" in scene 1, don't call it "Violation Doors" in scene 20. Record the canonical term in **GLOSSARY.md** and stick to it.

### 3. Update ContAnchors First
When you revise a scene and change a fact (a number, a state, a measurement), update **ContAnchors** immediately. Then search your entire project for that term to find other scenes that might need adjustment.

### 4. Scene IDs Are Stable
If you rearrange scenes, keep their IDs. Update **Prev/Next** pointers and **TIMELINE.md**, but don't renumber unless you have a deliberate plan.

### 5. Strip @@META for Final Compile
The metadata block is for you and the tool—readers don't see it. Your final compile script should remove everything from `@@META` to `@@END`.

---

## Common Pitfalls

❌ **Forgetting to update Prev/Next** If you insert or rearrange scenes, the chain breaks  
✅ Update **Prev/Next** and **TIMELINE.md** together

❌ **Inconsistent terms** "barrier," "gates," "walls" all refer to the same thing  
✅ Choose one term, record it in **GLOSSARY.md**, use it everywhere

❌ **Vague ContAnchors** "Amelia is injured"  
✅ Be specific: "Amelia_left_arm=broken; bloodloss=moderate; mobility=limping"

❌ **Numbers drift** Scene 5 says "12 soldiers," scene 7 says "15 soldiers," no explanation  
✅ Use ContAnchors: `soldier_count=12` and track changes explicitly

---

## See Also

- **[Index Files Guide](index-files.md)** How to maintain CANON.md, CAST.md, etc.
- **[Getting Started](getting-started.md)** Project setup walkthrough
- **[Templates](templates/)** Annotated template files
- **[Working with Findings](working-with-findings.md)** Understanding the tool's feedback
