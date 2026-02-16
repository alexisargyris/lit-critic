"""Tests for platform session state-machine helpers."""

from lit_platform.session_state_machine import (
    apply_acceptance,
    apply_discussion_outcome_reason,
    apply_finding_revision,
    apply_re_evaluation_result,
    all_findings_considered,
    apply_discussion_status,
    describe_revision_changes,
    apply_rejection,
    first_unresolved_index,
    is_terminal_status,
    next_available_index,
    next_index_for_lens,
    prior_outcomes_summary,
    learning_session_payload,
    record_discussion_acceptance,
    record_discussion_rejection,
    record_ambiguity_answer,
    restore_learning_session,
)
from lit_platform.runtime.models import LearningData
from lit_platform.runtime.models import Finding


def _finding(status: str = "pending") -> Finding:
    return Finding(
        number=1,
        severity="major",
        lens="prose",
        location="P1",
        evidence="E",
        impact="I",
        options=["O"],
        flagged_by=["prose"],
        status=status,
    )


def test_is_terminal_status():
    assert is_terminal_status("accepted") is True
    assert is_terminal_status("rejected") is True
    assert is_terminal_status("withdrawn") is True
    assert is_terminal_status("pending") is False


def test_first_unresolved_index():
    findings = [_finding("accepted"), _finding("pending"), _finding("withdrawn")]
    assert first_unresolved_index(findings) == 1


def test_all_findings_considered_requires_terminal_statuses():
    terminal = [_finding("accepted"), _finding("rejected"), _finding("withdrawn")]
    mixed = [_finding("accepted"), _finding("pending")]

    assert all_findings_considered(terminal) is True
    assert all_findings_considered(mixed) is False


def test_next_index_for_lens_structure_skips_prose_only():
    findings = [_finding("pending") for _ in range(4)]
    findings[1].lens = "prose"
    findings[2].lens = "structure"
    findings[3].lens = "coherence"

    assert next_index_for_lens(findings, 0, "structure") == 2


def test_next_index_for_lens_coherence_skips_prose_and_structure():
    findings = [_finding("pending") for _ in range(5)]
    findings[1].lens = "prose"
    findings[2].lens = "structure"
    findings[3].lens = "structure"
    findings[4].lens = "coherence"

    assert next_index_for_lens(findings, 0, "coherence") == 4


def test_next_available_index_skips_withdrawn_only():
    findings = [_finding("pending") for _ in range(4)]
    findings[0].status = "withdrawn"
    findings[1].status = "withdrawn"
    findings[2].status = "pending"

    assert next_available_index(findings, 0) == 2
    assert next_available_index(findings, 2) == 2


def test_apply_discussion_status_conceded_maps_to_withdrawn():
    finding = _finding("pending")
    apply_discussion_status(finding, "conceded")
    assert finding.status == "withdrawn"


def test_apply_discussion_outcome_reason_for_accepted():
    finding = _finding("pending")

    apply_discussion_outcome_reason(
        finding,
        "accepted",
        response_text="great",
        user_message="ok",
    )

    assert finding.outcome_reason == "Accepted by author"


def test_apply_discussion_outcome_reason_for_rejected_uses_user_message_excerpt():
    finding = _finding("pending")

    apply_discussion_outcome_reason(
        finding,
        "rejected",
        response_text="noted",
        user_message="This is intentional for voice",
    )

    assert finding.outcome_reason == "Rejected by author: This is intentional for voice"


def test_apply_discussion_outcome_reason_for_revised_uses_change_desc():
    finding = _finding("pending")

    apply_discussion_outcome_reason(
        finding,
        "revised",
        response_text="updated",
        user_message="thanks",
        change_desc="severity major → minor",
    )

    assert finding.outcome_reason == "Revised: severity major → minor"


def test_apply_finding_revision_updates_fields_and_tracks_history():
    finding = _finding("pending")
    finding.severity = "major"
    finding.evidence = "old evidence"
    finding.impact = "old impact"
    finding.options = ["old option"]

    old = apply_finding_revision(
        finding,
        {"severity": "minor", "impact": "new impact", "options": ["new option"]},
    )

    assert old == {
        "severity": "major",
        "evidence": "old evidence",
        "impact": "old impact",
        "options": ["old option"],
    }
    assert finding.severity == "minor"
    assert finding.impact == "new impact"
    assert finding.options == ["new option"]
    assert finding.revision_history[-1] == old


def test_describe_revision_changes_summarizes_delta():
    summary = describe_revision_changes(
        {"severity": "major"},
        {"severity": "minor", "impact": "new", "options": ["x"]},
    )

    assert "severity major → minor" in summary
    assert "impact updated" in summary
    assert "options updated" in summary


def test_apply_re_evaluation_result_updated_updates_fields_and_clears_stale():
    finding = _finding("pending")
    finding.stale = True

    result = apply_re_evaluation_result(
        finding,
        {
            "status": "updated",
            "line_start": 10,
            "line_end": 12,
            "location": "P2",
            "evidence": "updated evidence",
            "severity": "minor",
        },
    )

    assert result == {"status": "updated", "finding_number": finding.number}
    assert finding.line_start == 10
    assert finding.line_end == 12
    assert finding.location == "P2"
    assert finding.evidence == "updated evidence"
    assert finding.severity == "minor"
    assert finding.stale is False


def test_apply_re_evaluation_result_withdrawn_marks_terminal_and_reason():
    finding = _finding("pending")
    finding.stale = True

    result = apply_re_evaluation_result(
        finding,
        {
            "status": "withdrawn",
            "reason": "issue resolved after edit",
        },
    )

    assert result == {
        "status": "withdrawn",
        "finding_number": finding.number,
        "reason": "issue resolved after edit",
    }
    assert finding.status == "withdrawn"
    assert finding.stale is False
    assert finding.outcome_reason == "Withdrawn after re-evaluation: issue resolved after edit"


def test_prior_outcomes_summary_includes_non_pending_except_current():
    current = _finding("pending")
    current.number = 3

    accepted = _finding("accepted")
    accepted.number = 1
    accepted.outcome_reason = "Accepted by author"

    rejected = _finding("rejected")
    rejected.number = 2
    rejected.author_response = "not an issue"

    pending_other = _finding("pending")
    pending_other.number = 4

    summary = prior_outcomes_summary(
        [accepted, rejected, current, pending_other],
        current_finding_number=current.number,
    )

    assert "Finding #1" in summary
    assert "ACCEPTED" in summary
    assert "Finding #2" in summary
    assert "REJECTED" in summary
    assert "Finding #3" not in summary
    assert "Finding #4" not in summary


def test_apply_acceptance_sets_status_and_tracks_learning():
    finding = _finding("pending")
    learning = LearningData()

    apply_acceptance(finding, learning)

    assert finding.status == "accepted"
    assert len(learning.session_acceptances) == 1
    assert learning.session_acceptances[0]["lens"] == finding.lens
    assert learning.session_acceptances[0]["pattern"] == finding.evidence


def test_apply_rejection_sets_status_reason_and_tracks_learning():
    finding = _finding("pending")
    learning = LearningData()

    apply_rejection(finding, learning, "style choice")

    assert finding.status == "rejected"
    assert finding.author_response == "style choice"
    assert len(learning.session_rejections) == 1
    assert learning.session_rejections[0]["lens"] == finding.lens
    assert learning.session_rejections[0]["reason"] == "style choice"


def test_record_ambiguity_answer_tracks_intentional_flag():
    finding = _finding("pending")
    learning = LearningData()

    record_ambiguity_answer(finding, learning, intentional=False)

    assert len(learning.session_ambiguity_answers) == 1
    assert learning.session_ambiguity_answers[0]["location"] == finding.location
    assert learning.session_ambiguity_answers[0]["description"] == finding.evidence
    assert learning.session_ambiguity_answers[0]["intentional"] is False


def test_record_discussion_rejection_tracks_reason_and_optional_preference():
    finding = _finding("pending")
    learning = LearningData()

    record_discussion_rejection(
        finding,
        learning,
        reason="author rationale",
        preference_rule="Author prefers fragment rhythm",
    )

    assert len(learning.session_rejections) == 1
    assert learning.session_rejections[0] == {
        "lens": finding.lens,
        "pattern": finding.evidence,
        "reason": "author rationale",
        "preference_rule": "Author prefers fragment rhythm",
    }


def test_record_discussion_acceptance_tracks_lens_and_pattern():
    finding = _finding("pending")
    learning = LearningData()

    record_discussion_acceptance(finding, learning)

    assert len(learning.session_acceptances) == 1
    assert learning.session_acceptances[0] == {
        "lens": finding.lens,
        "pattern": finding.evidence,
    }


def test_restore_learning_session_populates_in_session_trackers():
    learning = LearningData()

    restore_learning_session(
        learning,
        {
            "session_rejections": [{"lens": "prose", "reason": "style"}],
            "session_acceptances": [{"lens": "clarity", "pattern": "E"}],
            "session_ambiguity_answers": [{"location": "P1", "intentional": True}],
        },
    )

    assert learning.session_rejections == [{"lens": "prose", "reason": "style"}]
    assert learning.session_acceptances == [{"lens": "clarity", "pattern": "E"}]
    assert learning.session_ambiguity_answers == [{"location": "P1", "intentional": True}]


def test_learning_session_payload_returns_serializable_shape():
    learning = LearningData()
    learning.session_rejections = [{"lens": "prose", "reason": "style"}]
    learning.session_acceptances = [{"lens": "clarity", "pattern": "E"}]
    learning.session_ambiguity_answers = [{"location": "P1", "intentional": True}]

    payload = learning_session_payload(learning)

    assert payload == {
        "session_rejections": [{"lens": "prose", "reason": "style"}],
        "session_acceptances": [{"lens": "clarity", "pattern": "E"}],
        "session_ambiguity_answers": [{"location": "P1", "intentional": True}],
    }
