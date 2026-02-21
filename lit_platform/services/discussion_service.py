"""Platform-owned discussion workflow service."""

import json
import re

from lit_platform.session_state_machine import (
    apply_discussion_outcome_reason,
    apply_finding_revision,
    describe_revision_changes,
    prior_outcomes_summary,
    record_ambiguity_answer,
    record_discussion_acceptance,
    record_discussion_rejection,
)
from lit_platform.runtime.llm import LLMResponse
from lit_platform.runtime.models import Finding, SessionState
from lit_platform.runtime.prompts import build_discussion_messages, get_discussion_system_prompt


def build_prior_outcomes_summary(state: SessionState, current_finding: Finding) -> str:
    """Build a compact summary of discussion outcomes for prior findings."""
    return prior_outcomes_summary(state.findings, current_finding.number)


def parse_discussion_response(response_text: str) -> dict:
    """Parse critic response for status/revision/preference/ambiguity tags."""
    result = {
        "display_text": response_text,
        "status": "continue",
        "revision": None,
        "preference": None,
        "ambiguity": None,
    }

    text = response_text

    revision_match = re.search(r"\[REVISION\]\s*(.*?)\s*\[/REVISION\]", text, re.DOTALL)
    if revision_match:
        try:
            result["revision"] = json.loads(revision_match.group(1).strip())
        except json.JSONDecodeError:
            pass
        text = text[:revision_match.start()] + text[revision_match.end():]

    preference_match = re.search(r"\[PREFERENCE:\s*(.*?)\]", text)
    if preference_match:
        result["preference"] = preference_match.group(1).strip()
        text = text[:preference_match.start()] + text[preference_match.end():]

    if "[AMBIGUITY:INTENTIONAL]" in text:
        result["ambiguity"] = "intentional"
        text = text.replace("[AMBIGUITY:INTENTIONAL]", "")
    elif "[AMBIGUITY:ACCIDENTAL]" in text:
        result["ambiguity"] = "accidental"
        text = text.replace("[AMBIGUITY:ACCIDENTAL]", "")

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
    """Apply revision data to a finding and preserve history."""
    return apply_finding_revision(finding, revision)


def _describe_changes(old: dict, revision: dict) -> str:
    """Generate human-readable revision change summary."""
    return describe_revision_changes(old, revision)


def _apply_discussion_side_effects(state: SessionState, finding: Finding,
                                   user_message: str, parsed: dict) -> tuple[str, str]:
    """Apply side effects from a parsed discussion response."""
    response_text = parsed["display_text"]
    status = parsed["status"]

    finding.discussion_turns.append({"role": "user", "content": user_message})
    finding.discussion_turns.append({"role": "assistant", "content": response_text})

    state.discussion_history.append({
        "finding_number": finding.number,
        "user": user_message,
        "assistant": response_text,
    })

    change_desc = None
    if status in ("revised", "escalated") and parsed["revision"]:
        old_version = apply_revision(finding, parsed["revision"])
        change_desc = _describe_changes(old_version, parsed["revision"])

    apply_discussion_outcome_reason(
        finding,
        status,
        response_text=response_text,
        user_message=user_message,
        change_desc=change_desc,
    )

    if parsed["ambiguity"]:
        intentional = parsed["ambiguity"] == "intentional"
        record_ambiguity_answer(
            finding,
            state.learning,
            intentional=intentional,
        )

    if status in ("rejected", "conceded", "withdrawn"):
        # "withdrawn" is included here as a fallback: the LLM may have
        # recognised an intentional stylistic choice without emitting a
        # [PREFERENCE:] tag.  Recording the rejection signal ensures the
        # learning database always captures something for terminal outcomes.
        # When [PREFERENCE:] IS present it is forwarded as preference_rule so
        # the stored description is richer; when absent, the evidence + reason
        # still form a useful preference entry.
        record_discussion_rejection(
            finding,
            state.learning,
            reason=user_message[:200],
            preference_rule=parsed["preference"],
        )
    elif status == "accepted":
        record_discussion_acceptance(finding, state.learning)
    elif parsed["preference"]:
        # Preference extracted without a terminal status (e.g., during revision)
        record_discussion_rejection(
            finding,
            state.learning,
            reason=user_message[:200],
            preference_rule=parsed["preference"],
        )

    return response_text, status


async def discuss_finding(state: SessionState, finding: Finding, user_message: str,
                          scene_changed: bool = False) -> tuple[str, str]:
    """Process discussion input and return ``(response_text, status)``."""
    prior_outcomes = build_prior_outcomes_summary(state, finding)
    system_prompt = get_discussion_system_prompt(finding, state.scene_content, prior_outcomes)

    api_message = user_message
    if scene_changed:
        api_message = (
            "[NOTE: The author has edited the scene text since the last message. "
            "The updated scene is shown in the system prompt. Acknowledge the "
            "changes if they are relevant to this finding.]\n\n" + user_message
        )

    messages = build_discussion_messages(finding, user_message, api_user_message=api_message)

    try:
        response = await state.effective_discussion_client.create_message(
            model=state.discussion_model_id,
            max_tokens=1024,
            messages=messages,
            system=system_prompt,
        )
        parsed = parse_discussion_response(response.text)
        return _apply_discussion_side_effects(state, finding, user_message, parsed)
    except Exception as e:
        return f"[Discussion error: {e}]", "continue"


async def discuss_finding_stream(state: SessionState, finding: Finding, user_message: str,
                                 scene_changed: bool = False):
    """Streaming discussion variant yielding ``(chunk_type, data)`` tuples."""
    prior_outcomes = build_prior_outcomes_summary(state, finding)
    system_prompt = get_discussion_system_prompt(finding, state.scene_content, prior_outcomes)

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
        async for item in state.effective_discussion_client.stream_message(
            model=state.discussion_model_id,
            max_tokens=1024,
            messages=messages,
            system=system_prompt,
        ):
            if isinstance(item, str):
                yield ("token", item)
            elif isinstance(item, LLMResponse):
                raw_response = item.text

        parsed = parse_discussion_response(raw_response)
        response_text, status = _apply_discussion_side_effects(
            state, finding, user_message, parsed
        )
        yield ("done", {"response": response_text, "status": status})
    except Exception as e:
        yield ("done", {"response": f"[Discussion error: {e}]", "status": "continue"})


__all__ = [
    "build_prior_outcomes_summary",
    "parse_discussion_response",
    "apply_revision",
    "discuss_finding",
    "discuss_finding_stream",
]
