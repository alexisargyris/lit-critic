"""
Discussion handler for the lit-critic system.
Handles interactive multi-turn dialogue between critic and author about findings.

Implements:
- Phase 1: Proper multi-turn conversations (system prompt + message pairs)
- Phase 2: Finding refinement (revise, withdraw, escalate)
- Phase 3: Cross-finding context (prior outcomes inform current discussion)
- Phase 4: Richer learning extraction (preference rules, structured reasons)
"""

import json
import re

from .llm import LLMResponse
from .models import SessionState, Finding
from .prompts import get_discussion_system_prompt, build_discussion_messages


def build_prior_outcomes_summary(state: SessionState, current_finding: Finding) -> str:
    """Build a compact summary of discussion outcomes for prior findings.
    
    This gives the critic context about what's already been discussed,
    preventing repetition of refuted arguments and providing continuity.
    (Phase 3: Cross-finding context)
    """
    outcomes = []
    for finding in state.findings:
        if finding.number == current_finding.number:
            continue
        if finding.status == "pending":
            continue
        
        status_desc = finding.status.upper()
        reason = ""
        if finding.outcome_reason:
            reason = f" — {finding.outcome_reason}"
        elif finding.author_response:
            reason = f" — author: \"{finding.author_response[:100]}\""
        
        outcomes.append(
            f"- Finding #{finding.number} ({finding.lens}, {finding.severity}): "
            f"{status_desc}{reason}"
        )
    
    if not outcomes:
        return ""
    
    return "\n".join(outcomes)


def parse_discussion_response(response_text: str) -> dict:
    """Parse the critic's response, extracting status, revision data, preference, and ambiguity.
    
    Returns dict with:
        - display_text: cleaned response for display
        - status: one of continue, accepted, rejected, conceded, revised, withdrawn, escalated
        - revision: dict of updated fields (or None)
        - preference: preference string (or None)
        - ambiguity: "intentional", "accidental", or None
    """
    result = {
        "display_text": response_text,
        "status": "continue",
        "revision": None,
        "preference": None,
        "ambiguity": None,
    }
    
    text = response_text
    
    # Extract revision block first (before stripping status tags)
    revision_match = re.search(r'\[REVISION\]\s*(.*?)\s*\[/REVISION\]', text, re.DOTALL)
    if revision_match:
        try:
            result["revision"] = json.loads(revision_match.group(1).strip())
        except json.JSONDecodeError:
            pass
        text = text[:revision_match.start()] + text[revision_match.end():]
    
    # Extract preference
    preference_match = re.search(r'\[PREFERENCE:\s*(.*?)\]', text)
    if preference_match:
        result["preference"] = preference_match.group(1).strip()
        text = text[:preference_match.start()] + text[preference_match.end():]
    
    # Extract ambiguity
    if "[AMBIGUITY:INTENTIONAL]" in text:
        result["ambiguity"] = "intentional"
        text = text.replace("[AMBIGUITY:INTENTIONAL]", "")
    elif "[AMBIGUITY:ACCIDENTAL]" in text:
        result["ambiguity"] = "accidental"
        text = text.replace("[AMBIGUITY:ACCIDENTAL]", "")
    
    # Extract status — check in priority order (more specific first)
    status_tags = {
        "[ESCALATED]": "escalated",
        "[REVISED]": "revised",
        "[WITHDRAWN]": "withdrawn",
        "[REJECTED]": "rejected",
        "[ACCEPTED]": "accepted",
        "[CONCEDED]": "conceded",
        "[CONTINUE]": "continue",
    }
    
    for tag, status in status_tags.items():
        if tag in text:
            result["status"] = status
            text = text.replace(tag, "")
            break
    
    result["display_text"] = text.strip()
    
    return result


def apply_revision(finding: Finding, revision: dict) -> dict:
    """Apply revision data to a finding, preserving the old version in revision_history.
    
    Returns the old version dict for reference.
    (Phase 2: Finding refinement)
    """
    # Save current state to revision history
    old_version = {
        "severity": finding.severity,
        "evidence": finding.evidence,
        "impact": finding.impact,
        "options": finding.options[:],
    }
    finding.revision_history.append(old_version)
    
    # Apply changes (only fields present in the revision)
    if "severity" in revision:
        finding.severity = revision["severity"]
    if "evidence" in revision:
        finding.evidence = revision["evidence"]
    if "impact" in revision:
        finding.impact = revision["impact"]
    if "options" in revision:
        finding.options = revision["options"]
    
    return old_version


def _describe_changes(old: dict, revision: dict) -> str:
    """Generate a human-readable description of what changed in a revision."""
    changes = []
    if "severity" in revision and revision["severity"] != old.get("severity"):
        changes.append(f"severity {old.get('severity', '?')} → {revision['severity']}")
    if "evidence" in revision:
        changes.append("evidence refined")
    if "impact" in revision:
        changes.append("impact updated")
    if "options" in revision:
        changes.append("options updated")
    return ", ".join(changes) if changes else "minor refinements"


def _apply_discussion_side_effects(state: SessionState, finding: Finding,
                                   user_message: str, parsed: dict) -> tuple[str, str]:
    """Apply all side effects from a parsed discussion response.
    
    Shared by both handle_discussion() and handle_discussion_stream() to avoid
    duplicating the post-response logic.
    
    Returns (response_text, status).
    """
    response_text = parsed["display_text"]
    status = parsed["status"]
    
    # Phase 1: Store proper conversation turns on the finding
    finding.discussion_turns.append({"role": "user", "content": user_message})
    finding.discussion_turns.append({"role": "assistant", "content": response_text})
    
    # Maintain state-level discussion history for backward compatibility
    state.discussion_history.append({
        "finding_number": finding.number,
        "user": user_message,
        "assistant": response_text
    })
    
    # Phase 2: Handle revision/escalation/withdrawal
    if status in ("revised", "escalated") and parsed["revision"]:
        old_version = apply_revision(finding, parsed["revision"])
        change_desc = _describe_changes(old_version, parsed["revision"])
        action = "Revised" if status == "revised" else "Escalated"
        finding.outcome_reason = f"{action}: {change_desc}"
    elif status == "withdrawn":
        finding.outcome_reason = f"Withdrawn by critic: {response_text[:150]}"
    elif status == "conceded":
        finding.outcome_reason = f"Conceded by critic: {response_text[:150]}"
    elif status == "rejected":
        finding.outcome_reason = f"Rejected by author: {user_message[:150]}"
    elif status == "accepted":
        finding.outcome_reason = "Accepted by author"
    
    # Handle ambiguity classification
    if parsed["ambiguity"]:
        intentional = parsed["ambiguity"] == "intentional"
        state.learning.session_ambiguity_answers.append({
            "location": finding.location,
            "description": finding.evidence[:100],
            "intentional": intentional
        })
    
    # Phase 4: Richer learning extraction
    if status in ("rejected", "conceded"):
        rejection_entry = {
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
            "reason": user_message[:200],
        }
        # Include explicit preference rule if the critic provided one
        if parsed["preference"]:
            rejection_entry["preference_rule"] = parsed["preference"]
        state.learning.session_rejections.append(rejection_entry)
    elif status == "accepted":
        state.learning.session_acceptances.append({
            "lens": finding.lens,
            "pattern": finding.evidence[:100]
        })
    elif parsed["preference"]:
        # Preference extracted even without a terminal status (e.g., during revision)
        state.learning.session_rejections.append({
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
            "reason": user_message[:200],
            "preference_rule": parsed["preference"],
        })
    
    return response_text, status


async def handle_discussion(state: SessionState, finding: Finding, user_message: str,
                            scene_changed: bool = False) -> tuple[str, str]:
    """
    Process author's discussion input and get critic's response using multi-turn conversation.
    
    Args:
        state: Current session state.
        finding: The finding being discussed.
        user_message: The author's message.
        scene_changed: If True, the scene file was edited since the last message.
            A note is prepended to the API message (not stored in turns) so the
            critic can acknowledge the edits.
    
    Returns (response_text, status) where status is one of:
        'continue', 'accepted', 'rejected', 'conceded', 'revised', 'withdrawn', 'escalated'
    
    Side effects:
        - Appends conversation turns to finding.discussion_turns
        - Updates finding fields on revision/escalation
        - Records outcome_reason on finding
        - Tracks learning data (rejections, acceptances, preferences, ambiguity)
        - Appends to state.discussion_history for backward compatibility
    """
    # Phase 3: Build cross-finding context
    prior_outcomes = build_prior_outcomes_summary(state, finding)
    
    # Phase 1: Build system prompt and proper multi-turn messages
    system_prompt = get_discussion_system_prompt(finding, state.scene_content, prior_outcomes)
    
    # If the scene was edited, prepend a note to the API message so the critic
    # is aware.  The original user_message is stored in discussion_turns (not
    # the augmented version).
    api_message = user_message
    if scene_changed:
        api_message = (
            "[NOTE: The author has edited the scene text since the last message. "
            "The updated scene is shown in the system prompt. Acknowledge the "
            "changes if they are relevant to this finding.]\n\n" + user_message
        )
    
    messages = build_discussion_messages(finding, user_message, api_user_message=api_message)
    
    try:
        response = await state.client.create_message(
            model=state.model_id,
            max_tokens=1024,
            messages=messages,
            system=system_prompt,
        )
        
        raw_response = response.text
        
        # Parse structured response and apply side effects
        parsed = parse_discussion_response(raw_response)
        return _apply_discussion_side_effects(state, finding, user_message, parsed)
        
    except Exception as e:
        return f"[Discussion error: {e}]", "continue"


async def handle_discussion_stream(state: SessionState, finding: Finding, user_message: str,
                                   scene_changed: bool = False):
    """
    Streaming variant of handle_discussion(). Yields tokens as they arrive from the API.
    
    This is an async generator that yields (chunk_type, data) tuples:
        ("token", text_chunk)  — a piece of the response text as it streams in
        ("done", result_dict)  — final result after stream completes
    
    The result_dict contains:
        - response: cleaned display text
        - status: discussion status string
    
    Args:
        scene_changed: If True, the scene file was edited since the last message.
    
    Side effects are applied after the stream completes (identical to handle_discussion).
    """
    # Phase 3: Build cross-finding context
    prior_outcomes = build_prior_outcomes_summary(state, finding)
    
    # Phase 1: Build system prompt and proper multi-turn messages
    system_prompt = get_discussion_system_prompt(finding, state.scene_content, prior_outcomes)
    
    # If the scene was edited, prepend a note to the API message
    api_message = user_message
    if scene_changed:
        api_message = (
            "[NOTE: The author has edited the scene text since the last message. "
            "The updated scene is shown in the system prompt. Acknowledge the "
            "changes if they are relevant to this finding.]\n\n" + user_message
        )
    
    messages = build_discussion_messages(finding, user_message, api_user_message=api_message)
    
    try:
        raw_response = ""
        async for item in state.client.stream_message(
            model=state.model_id,
            max_tokens=1024,
            messages=messages,
            system=system_prompt,
        ):
            if isinstance(item, str):
                yield ("token", item)
            elif isinstance(item, LLMResponse):
                raw_response = item.text

        # Parse structured response and apply side effects
        parsed = parse_discussion_response(raw_response)
        response_text, status = _apply_discussion_side_effects(
            state, finding, user_message, parsed
        )
        
        yield ("done", {"response": response_text, "status": status})
        
    except Exception as e:
        yield ("done", {"response": f"[Discussion error: {e}]", "status": "continue"})
