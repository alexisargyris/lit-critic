"""Platform-owned session state machine helpers."""

from __future__ import annotations

from typing import Optional

from lit_platform.runtime.models import Finding, LearningData


TERMINAL_STATUSES = {"accepted", "rejected", "withdrawn"}


def is_terminal_status(status: str) -> bool:
    """Return True when a finding status is terminal."""
    return (status or "pending") in TERMINAL_STATUSES


def first_unresolved_index(findings: list[Finding]) -> Optional[int]:
    """Return first non-terminal finding index, or None."""
    for i, finding in enumerate(findings):
        if not is_terminal_status(finding.status):
            return i
    return None


def all_findings_considered(findings: list[Finding]) -> bool:
    """Return True when every finding has a terminal status."""
    return all(is_terminal_status(f.status) for f in findings)


def next_index_for_lens(findings: list[Finding], current_index: int, target_lens: str) -> int:
    """Return the next index after applying lens-group skip semantics."""
    idx = current_index + 1
    while idx < len(findings):
        lens = (findings[idx].lens or "").lower()
        if target_lens == "structure" and lens == "prose":
            idx += 1
            continue
        if target_lens == "coherence" and lens in ("prose", "structure"):
            idx += 1
            continue
        break
    return idx


def next_available_index(findings: list[Finding], start_index: int) -> int:
    """Return first index at/after start that is not withdrawn (or len(findings))."""
    idx = start_index
    while idx < len(findings) and findings[idx].status == "withdrawn":
        idx += 1
    return idx


def apply_discussion_status(finding: Finding, status: str) -> None:
    """Apply discussion status to finding using canonical persisted states."""
    if status == "accepted":
        finding.status = "accepted"
    elif status == "conceded":
        finding.status = "withdrawn"
    elif status == "rejected":
        finding.status = "rejected"
    elif status == "revised":
        finding.status = "revised"
    elif status == "withdrawn":
        finding.status = "withdrawn"
    elif status == "escalated":
        finding.status = "escalated"


def apply_discussion_outcome_reason(
    finding: Finding,
    status: str,
    *,
    response_text: str,
    user_message: str,
    change_desc: str | None = None,
) -> None:
    """Apply canonical discussion outcome reason text to a finding."""
    if status in ("revised", "escalated") and change_desc:
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


def apply_finding_revision(finding: Finding, revision: dict) -> dict:
    """Apply a revision payload to a finding, returning its previous snapshot."""
    old_version = {
        "severity": finding.severity,
        "evidence": finding.evidence,
        "impact": finding.impact,
        "options": finding.options[:],
    }
    finding.revision_history.append(old_version)

    if "severity" in revision:
        finding.severity = revision["severity"]
    if "evidence" in revision:
        finding.evidence = revision["evidence"]
    if "impact" in revision:
        finding.impact = revision["impact"]
    if "options" in revision:
        finding.options = revision["options"]

    return old_version


def describe_revision_changes(old: dict, revision: dict) -> str:
    """Generate a concise human-readable summary of revision deltas."""
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


def apply_re_evaluation_result(finding: Finding, result: dict) -> dict:
    """Apply a re-evaluation result payload to a finding and return API-style outcome."""
    status = result.get("status")

    if status == "updated":
        finding.line_start = result.get("line_start", finding.line_start)
        finding.line_end = result.get("line_end", finding.line_end)
        finding.location = result.get("location", finding.location)
        if result.get("evidence"):
            finding.evidence = result["evidence"]
        severity = result.get("severity")
        if severity in {"critical", "major", "minor"}:
            finding.severity = severity
        finding.stale = False
        return {"status": "updated", "finding_number": finding.number}

    if status == "withdrawn":
        finding.status = "withdrawn"
        finding.stale = False
        finding.outcome_reason = (
            "Withdrawn after re-evaluation: "
            f"{result.get('reason', 'edit resolved the issue')}"
        )
        return {
            "status": "withdrawn",
            "finding_number": finding.number,
            "reason": result.get("reason", ""),
        }

    finding.stale = False
    return {
        "status": "error",
        "finding_number": finding.number,
        "error": f"Unexpected status: {status}",
    }


def prior_outcomes_summary(findings: list[Finding], current_finding_number: int) -> str:
    """Build compact prior-findings outcome summary for discussion context."""
    outcomes = []
    for finding in findings:
        if finding.number == current_finding_number:
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


def apply_acceptance(finding: Finding, learning: LearningData) -> None:
    """Mark finding accepted and record acceptance learning signal."""
    finding.status = "accepted"
    learning.session_acceptances.append(
        {
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
        }
    )


def apply_rejection(finding: Finding, learning: LearningData, reason: str = "") -> None:
    """Mark finding rejected and record rejection learning signal."""
    finding.status = "rejected"
    finding.author_response = reason
    learning.session_rejections.append(
        {
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
            "reason": reason,
        }
    )


def record_discussion_rejection(
    finding: Finding,
    learning: LearningData,
    *,
    reason: str,
    preference_rule: str | None = None,
) -> None:
    """Record discussion-derived rejection/concession learning signal."""
    rejection_entry = {
        "lens": finding.lens,
        "pattern": finding.evidence[:100],
        "reason": reason,
    }
    if preference_rule:
        rejection_entry["preference_rule"] = preference_rule
    learning.session_rejections.append(rejection_entry)


def record_discussion_acceptance(finding: Finding, learning: LearningData) -> None:
    """Record discussion-derived acceptance learning signal."""
    learning.session_acceptances.append(
        {
            "lens": finding.lens,
            "pattern": finding.evidence[:100],
        }
    )


def record_ambiguity_answer(
    finding: Finding,
    learning: LearningData,
    *,
    intentional: bool,
) -> None:
    """Record author ambiguity classification for learning extraction."""
    learning.session_ambiguity_answers.append(
        {
            "location": finding.location,
            "description": finding.evidence[:100],
            "intentional": intentional,
        }
    )


def restore_learning_session(learning: LearningData, learning_session: dict) -> LearningData:
    """Restore in-session learning trackers from persisted session payload."""
    learning.session_rejections = learning_session.get("session_rejections", [])
    learning.session_acceptances = learning_session.get("session_acceptances", [])
    learning.session_ambiguity_answers = learning_session.get("session_ambiguity_answers", [])
    return learning


def learning_session_payload(learning: LearningData) -> dict:
    """Build serializable in-session learning payload for persistence."""
    return {
        "session_rejections": learning.session_rejections,
        "session_acceptances": learning.session_acceptances,
        "session_ambiguity_answers": learning.session_ambiguity_answers,
    }
