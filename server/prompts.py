"""
Prompt templates for the lit-critic lenses and coordinator.
"""

from .utils import number_lines


def get_lens_prompt(lens_name: str, scene: str, indexes: dict[str, str]) -> str:
    """Generate the prompt for a specific lens."""
    
    numbered_scene = number_lines(scene)
    
    base_context = f"""You are one lens in a multi-lens editorial review system for fiction manuscripts.
Your lens: {lens_name.upper()}

You will analyze the scene and output findings in a specific structured format.
Respond ONLY with the structured output. No preamble, no explanation, no summary.

## INDEX FILES

### CANON.md
{indexes.get('CANON.md', '[Not provided]')}

### CAST.md
{indexes.get('CAST.md', '[Not provided]')}

### GLOSSARY.md
{indexes.get('GLOSSARY.md', '[Not provided]')}

### STYLE.md
{indexes.get('STYLE.md', '[Not provided]')}

### THREADS.md
{indexes.get('THREADS.md', '[Not provided]')}

### TIMELINE.md
{indexes.get('TIMELINE.md', '[Not provided]')}

### LEARNING.md (author preferences from past sessions)
{indexes.get('LEARNING.md', '[No learned preferences yet]')}

## SCENE TO ANALYZE

The scene text below has line numbers (L001, L002, …). Use these line numbers in your
``location`` field and in ``line_start``/``line_end`` so findings can be mapped to exact
editor positions.

{numbered_scene}
"""

    lens_instructions = {
        "prose": """## YOUR TASK: PROSE LENS

Focus ONLY on sentence-level and paragraph-level craft:
- Fluidity and rhythm (reader should "slip through" without effort)
- Voice consistency within the scene
- Register per STYLE.md (present-timeline: dry/concrete; past-timeline: lyrical)
- Awkward constructions, repetition, clunky transitions
- Overwriting/underwriting relative to tension

IMPORTANT: Check LEARNING.md for author preferences. Do NOT flag issues that match patterns the author has previously rejected.

## OUTPUT FORMAT

Output a JSON array of findings. Each finding must have:
- severity: "critical" | "major" | "minor"
- location: human-readable reference including the line range (e.g. "L042-L045, starting 'She moved...'")
- line_start: integer, first line number of the issue (from the L-prefixed numbers in the scene)
- line_end: integer, last line number of the issue
- evidence: why this is a problem (be specific)
- impact: why it matters to the reader
- options: array of 1-2 action suggestions (NOT replacement prose)

Example:
```json
[
  {
    "severity": "major",
    "location": "L007-L009, starting 'She moved...'",
    "line_start": 7,
    "line_end": 9,
    "evidence": "Three consecutive sentences begin with 'She', creating monotonous rhythm",
    "impact": "Reader notices the repetition, breaking immersion",
    "options": ["Vary sentence openings", "Combine two sentences to break the pattern"]
  }
]
```

If no issues found, output: []
Output ONLY the JSON array, nothing else.""",

        "structure": """## YOUR TASK: STRUCTURE LENS

Focus ONLY on scene function and narrative advancement:
- Scene objective (compare to header's Objective field if present)
- Threads mentioned in header are actually touched (cross-ref THREADS.md)
- Pacing appropriate to position in TIMELINE.md
- Stakes present; promises made or paid off
- Late entry / early exit principles
- Dead weight passages that don't serve the scene objective

IMPORTANT: Check LEARNING.md for author preferences.

## OUTPUT FORMAT

Output a JSON array of findings. Each finding must have:
- severity: "critical" | "major" | "minor"
- location: human-readable reference including the line range (e.g. "L012-L025, mid-scene pacing lull")
- line_start: integer, first line number of the issue
- line_end: integer, last line number of the issue
- evidence: why this is a problem (cite index files if relevant)
- impact: why it matters to the reader
- options: array of 1-2 action suggestions

If no issues found, output: []
Output ONLY the JSON array, nothing else.""",

        "logic": """## YOUR TASK: LOGIC LENS

Focus ONLY on whether actions, motivations, and mechanics make sense:
- Character actions consistent with established traits (cross-ref CAST.md)
- Motivations legible (inferable, not necessarily explicit)
- Cause-effect chains hold
- Worldbuilding mechanics applied correctly (cross-ref CANON.md)
- No "idiot plot" moments (characters acting unreasonably stupid to enable plot)

IMPORTANT: Check LEARNING.md for author preferences.

## OUTPUT FORMAT

Output a JSON array of findings. Each finding must have:
- severity: "critical" | "major" | "minor"
- location: human-readable reference including the line range (e.g. "L018-L022, Elena's reaction")
- line_start: integer, first line number of the issue
- line_end: integer, last line number of the issue
- evidence: why this is a problem (cite CAST.md or CANON.md if relevant)
- impact: why it matters to the reader
- options: array of 1-2 action suggestions

If no issues found, output: []
Output ONLY the JSON array, nothing else.""",

        "clarity": """## YOUR TASK: CLARITY LENS

Focus ONLY on whether a reader can follow what's happening:
- Referent clarity: pronouns, "the X" references, who's speaking
- Spatial/temporal grounding: can reader picture where/when?
- Action legibility: is it clear what physically happens?
- Information sufficiency: does reader have what they need?

For ambiguous passages, note whether ambiguity seems intentional or accidental.
Check LEARNING.md for patterns the author has marked as intentional ambiguity.

## OUTPUT FORMAT

Output a JSON array of findings. Each finding must have:
- severity: "critical" | "major" | "minor"
- location: human-readable reference including the line range (e.g. "L031-L033, unclear 'she' referent")
- line_start: integer, first line number of the issue
- line_end: integer, last line number of the issue
- evidence: why this is a problem
- impact: what confusion results for the reader
- options: array of 1-2 action suggestions
- ambiguity_type: "unclear" | "ambiguous_possibly_intentional" | null

If no issues found, output: []
Output ONLY the JSON array, nothing else.""",

        "continuity": """## YOUR TASK: CONTINUITY LENS

Focus ONLY on factual consistency with established canon:
- Terms match GLOSSARY.md spelling and definition
- Facts about characters match CAST.md
- World rules from CANON.md are not violated
- ContAnchors in header (if present) match text
- Timeline position coherent with TIMELINE.md

Also flag:
- Terms that appear inconsistently spelled
- Potential new terms not in GLOSSARY.md
- Usage that contradicts GLOSSARY.md definitions

## OUTPUT FORMAT

Output a JSON object with two arrays:

```json
{
  "glossary_issues": [
    "Term X spelled as Y but GLOSSARY.md says Z",
    "Potential new term: ABC (appears 3 times, not in glossary)"
  ],
  "findings": [
    {
      "severity": "major",
      "location": "L028, character age reference",
      "line_start": 28,
      "line_end": 28,
      "evidence": "Character described as 30 years old but CAST.md says 24",
      "impact": "Continuity error readers may notice",
      "options": ["Correct age to match CAST.md", "Update CAST.md if age change is intentional"]
    }
  ]
}
```

If no issues found, output: {"glossary_issues": [], "findings": []}
Output ONLY the JSON object, nothing else.""",
    }
    
    return base_context + lens_instructions[lens_name]


# --- Coordinator tool schema (forces structured output via Anthropic tool_use) ---

COORDINATOR_TOOL = {
    "name": "report_findings",
    "description": "Report the coordinated editorial findings after deduplication, conflict detection, and prioritisation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "glossary_issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Glossary issues surfaced by the continuity lens."
            },
            "summary": {
                "type": "object",
                "description": "Finding counts by lens group and severity.",
                "properties": {
                    "prose": {
                        "type": "object",
                        "properties": {
                            "critical": {"type": "integer"},
                            "major": {"type": "integer"},
                            "minor": {"type": "integer"}
                        },
                        "required": ["critical", "major", "minor"]
                    },
                    "structure": {
                        "type": "object",
                        "properties": {
                            "critical": {"type": "integer"},
                            "major": {"type": "integer"},
                            "minor": {"type": "integer"}
                        },
                        "required": ["critical", "major", "minor"]
                    },
                    "coherence": {
                        "type": "object",
                        "properties": {
                            "critical": {"type": "integer"},
                            "major": {"type": "integer"},
                            "minor": {"type": "integer"}
                        },
                        "required": ["critical", "major", "minor"]
                    }
                },
                "required": ["prose", "structure", "coherence"]
            },
            "conflicts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Descriptions of conflicts between lenses."
            },
            "ambiguities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Possibly-intentional ambiguities to confirm with the author."
            },
            "findings": {
                "type": "array",
                "description": "Deduplicated, prioritised findings sorted by lens group then severity.",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer", "description": "Sequential finding number."},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "major", "minor"]
                        },
                        "lens": {
                            "type": "string",
                            "enum": ["prose", "structure", "logic", "clarity", "continuity"],
                            "description": "Primary lens for this finding."
                        },
                        "location": {"type": "string", "description": "Human-readable location including line range (e.g. 'L042-L045, starting She moved...')."},
                        "line_start": {
                            "type": ["integer", "null"],
                            "description": "First line number of the issue (1-based), or null if not applicable."
                        },
                        "line_end": {
                            "type": ["integer", "null"],
                            "description": "Last line number of the issue (1-based), or null if not applicable."
                        },
                        "evidence": {"type": "string", "description": "Why this is a problem."},
                        "impact": {"type": "string", "description": "Why it matters to the reader."},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "1-2 action suggestions."
                        },
                        "flagged_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Which lenses flagged this issue."
                        },
                        "ambiguity_type": {
                            "type": ["string", "null"],
                            "enum": ["unclear", "ambiguous_possibly_intentional", None],
                            "description": "Ambiguity classification, if applicable."
                        }
                    },
                    "required": ["number", "severity", "lens", "location", "evidence", "impact", "options"]
                }
            }
        },
        "required": ["glossary_issues", "summary", "conflicts", "ambiguities", "findings"]
    }
}


# Lens group definitions for chunked coordinator calls
LENS_GROUPS = {
    "prose":     {"lenses": ["prose"],                        "label": "Prose"},
    "structure": {"lenses": ["structure"],                    "label": "Structure"},
    "coherence": {"lenses": ["logic", "clarity", "continuity"], "label": "Coherence (Logic + Clarity + Continuity)"},
}


def get_coordinator_prompt(lens_results: list, scene: str) -> str:
    """Generate the prompt for the coordinator to merge and prioritize findings.

    The coordinator is invoked with tool_use (COORDINATOR_TOOL) so it does NOT
    need to emit raw JSON.  The prompt focuses on the editorial task only.
    """

    numbered_scene = number_lines(scene)

    results_text = ""
    for result in lens_results:
        results_text += f"\n### {result.lens_name.upper()} LENS OUTPUT\n"
        results_text += result.raw_output + "\n"

    return f"""You are the coordinator for a multi-lens editorial review system.

Five lenses have analyzed a scene. Your job is to:
1. Parse their outputs
2. Deduplicate (same issue flagged by multiple lenses → merge, note which lenses in flagged_by)
3. Detect conflicts (lenses disagree → flag for author decision)
4. Prioritize: Prose first, then Structure, then Coherence (Logic+Clarity+Continuity together)
5. Number the final findings sequentially
6. **Preserve line_start and line_end** from lens outputs — these are critical for editor integration

Sort findings by priority:
1. All prose findings (critical → major → minor)
2. All structure findings (critical → major → minor)
3. All coherence findings (critical → major → minor)

When merging duplicate findings from multiple lenses, keep the most specific line_start/line_end
range. If lenses report different ranges for the same issue, use the tightest (most specific) range.

Use the report_findings tool to submit your coordinated results.

## SCENE (with line numbers for reference)

{numbered_scene}

## LENS OUTPUTS
{results_text}"""


def get_coordinator_chunk_prompt(group_name: str, group_results: list, scene: str) -> str:
    """Generate a coordinator prompt for a single lens group (chunked mode).

    This is a smaller, focused coordinator call that only handles findings from
    one lens group at a time (prose, structure, or coherence).  Each chunk
    deduplicates within the group and outputs numbered findings.  The caller
    is responsible for renumbering across chunks.
    """
    group = LENS_GROUPS[group_name]
    numbered_scene = number_lines(scene)

    results_text = ""
    for result in group_results:
        results_text += f"\n### {result.lens_name.upper()} LENS OUTPUT\n"
        results_text += result.raw_output + "\n"

    coherence_note = ""
    if group_name == "coherence":
        coherence_note = """
These three lenses often flag the same passage from different angles.
Aggressively merge duplicates: if Logic and Clarity both flag the same line range,
combine into a single finding and list both in flagged_by.
"""

    return f"""You are the coordinator for a multi-lens editorial review system.
You are processing the **{group["label"]}** lens group.

Your job for this group:
1. Parse the lens output(s) below
2. Deduplicate (same issue flagged by multiple lenses → merge, note which lenses in flagged_by)
3. Detect any conflicts between lenses in this group
4. Sort findings by severity: critical → major → minor
5. Number findings sequentially starting from 1 (the caller will renumber across groups)
6. **Preserve line_start and line_end** these are critical for editor integration
{coherence_note}
When merging duplicate findings, keep the most specific line_start/line_end range.

Use the report_findings tool to submit your coordinated results.
Set glossary_issues to [] unless this is the coherence group (which includes continuity lens findings).

## SCENE (with line numbers for reference)

{numbered_scene}

## LENS OUTPUTS
{results_text}"""


def get_discussion_system_prompt(finding, scene_content: str, prior_outcomes: str = "") -> str:
    """Generate system prompt for multi-turn discussion about a finding.
    
    This is used as the 'system' parameter in the API call, providing stable context
    for the entire conversation. The actual conversation turns are sent as messages.
    """
    
    prior_section = ""
    if prior_outcomes:
        prior_section = f"""
## PRIOR DISCUSSION OUTCOMES

{prior_outcomes}

Take these into account. Do not repeat arguments the author has already addressed in prior findings.
"""

    return f"""You are an editorial critic in a multi-turn discussion with the author about a specific finding from your review.

## THE FINDING BEING DISCUSSED

Number: {finding.number}
Severity: {finding.severity}
Lens: {finding.lens}
Location: {finding.location}
Line range: {f"L{finding.line_start}" + (f"-L{finding.line_end}" if finding.line_end and finding.line_end != finding.line_start else "") if finding.line_start else "not specified"}
Evidence: {finding.evidence}
Impact: {finding.impact}
Options: {', '.join(finding.options)}

## FULL SCENE TEXT (with line numbers)

{number_lines(scene_content)}
{prior_section}
## YOUR ROLE

You are having a genuine editorial discussion. You may:
- Defend the finding with specific evidence from the text
- Concede if the author makes a good argument
- Propose a compromise (revise severity, refine the issue)
- Withdraw the finding entirely if convinced it was incorrect
- Escalate severity if discussion reveals the issue is worse than initially assessed
- Ask ONE clarifying question if needed

Be concise (2-4 sentences of natural response). Do not lecture.

## RESPONSE FORMAT

End your response with exactly ONE status tag:
- [CONTINUE] — discussion should continue
- [ACCEPTED] — author accepts the finding and will address it
- [REJECTED] — author is clearly rejecting this finding
- [CONCEDED] — you're conceding the point (you were wrong or the author's argument is convincing)
- [REVISED] — you're revising the finding based on discussion (changed severity, refined evidence, etc.)
- [WITHDRAWN] — you're withdrawing the finding entirely (it was incorrect)
- [ESCALATED] — discussion revealed this is more serious than initially assessed

If using [REVISED] or [ESCALATED], include a revision block immediately after with ONLY the fields that changed:
[REVISION]
{{"severity": "new_severity", "evidence": "refined evidence", "impact": "refined impact", "options": ["refined options"]}}
[/REVISION]

If this finding involves ambiguity and the author clarifies, also include:
[AMBIGUITY:INTENTIONAL] or [AMBIGUITY:ACCIDENTAL]

If this interaction reveals a general author preference (not scene-specific), include:
[PREFERENCE: one-line description of the preference for future reviews]"""


def build_discussion_messages(finding, user_message: str,
                              api_user_message: str | None = None) -> list[dict]:
    """Build proper multi-turn message list from finding's discussion history plus new user message.
    
    Args:
        finding: The finding being discussed (contains prior turns).
        user_message: The author's message (stored in discussion_turns).
        api_user_message: Optional augmented version of the message to send to
            the API.  When provided, this is used as the content of the final
            user message instead of *user_message*.  This allows injecting
            context notes (e.g. scene-change notifications) without polluting
            the stored conversation history.
    
    Returns a list of {role, content} dicts suitable for the Anthropic messages API.
    """
    messages = []
    
    # Add existing conversation turns from this finding
    for turn in finding.discussion_turns:
        messages.append({
            "role": turn["role"],
            "content": turn["content"]
        })
    
    # Add the new user message (use augmented version for API if provided)
    messages.append({
        "role": "user",
        "content": api_user_message if api_user_message is not None else user_message
    })
    
    return messages


def get_re_evaluation_prompt(finding, scene_content: str) -> str:
    """Generate prompt for re-evaluating a stale finding against updated scene text.

    This is used when the author edits the scene file during a session and a finding's
    line range overlaps the edited region.  A single focused API call determines whether
    the finding is still valid.
    """
    numbered_scene = number_lines(scene_content)

    return f"""You are an editorial critic re-evaluating a single finding after the author edited the scene.

## ORIGINAL FINDING

Number: {finding.number}
Severity: {finding.severity}
Lens: {finding.lens}
Location: {finding.location}
Original line range: L{finding.line_start or '?'}-L{finding.line_end or '?'}
Evidence: {finding.evidence}
Impact: {finding.impact}
Options: {', '.join(finding.options)}

## UPDATED SCENE TEXT (with new line numbers)

{numbered_scene}

## YOUR TASK

The author has edited the scene since this finding was raised. The text in the original
line range has changed. Determine:

1. Is this finding **still valid** in the updated text?
2. If yes: provide updated line_start, line_end, location, and (if needed) revised evidence.
3. If no: the edit resolved the issue — withdraw the finding.

Respond with a JSON object in exactly one of these two forms:

**If still valid (updated):**
```json
{{
  "status": "updated",
  "line_start": <new integer>,
  "line_end": <new integer>,
  "location": "<updated human-readable location>",
  "evidence": "<updated evidence if changed, or original if unchanged>",
  "severity": "<same or adjusted severity>"
}}
```

**If resolved (withdrawn):**
```json
{{
  "status": "withdrawn",
  "reason": "<brief explanation of why the edit resolved this issue>"
}}
```

Output ONLY the JSON object, nothing else."""
