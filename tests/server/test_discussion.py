"""
Tests for lit-critic.discussion module.

Covers all 4 phases:
- Phase 1: Multi-turn conversations (system prompt + message pairs)
- Phase 2: Finding refinement (revise, withdraw, escalate)
- Phase 3: Cross-finding context (prior outcomes summary)
- Phase 4: Richer learning extraction (preference rules)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from lit_platform.runtime.discussion import (
    handle_discussion,
    handle_discussion_stream,
    parse_discussion_response,
    build_prior_outcomes_summary,
    apply_revision,
    _apply_discussion_side_effects,
    _describe_changes,
)
from lit_platform.runtime.models import Finding


class TestParseDiscussionResponse:
    """Tests for parse_discussion_response (pure function, no mocks needed)."""

    def test_extracts_continue_status(self):
        parsed = parse_discussion_response("Let me explain. [CONTINUE]")
        assert parsed["status"] == "continue"
        assert "[CONTINUE]" not in parsed["display_text"]

    def test_extracts_accepted_status(self):
        parsed = parse_discussion_response("Great, noted. [ACCEPTED]")
        assert parsed["status"] == "accepted"
        assert "[ACCEPTED]" not in parsed["display_text"]

    def test_extracts_rejected_status(self):
        parsed = parse_discussion_response("I see your point. [REJECTED]")
        assert parsed["status"] == "rejected"

    def test_extracts_conceded_status(self):
        parsed = parse_discussion_response("You're right. [CONCEDED]")
        assert parsed["status"] == "conceded"

    def test_extracts_revised_status(self):
        parsed = parse_discussion_response("Fair point, let me revise. [REVISED]")
        assert parsed["status"] == "revised"

    def test_extracts_withdrawn_status(self):
        parsed = parse_discussion_response("I was wrong about this. [WITHDRAWN]")
        assert parsed["status"] == "withdrawn"

    def test_extracts_escalated_status(self):
        parsed = parse_discussion_response("Actually this is worse. [ESCALATED]")
        assert parsed["status"] == "escalated"

    def test_default_status_is_continue(self):
        parsed = parse_discussion_response("Let me think about that.")
        assert parsed["status"] == "continue"

    def test_extracts_revision_block(self):
        text = 'Fair point. [REVISED]\n[REVISION]\n{"severity": "minor", "impact": "Less severe"}\n[/REVISION]'
        parsed = parse_discussion_response(text)
        assert parsed["status"] == "revised"
        assert parsed["revision"] is not None
        assert parsed["revision"]["severity"] == "minor"
        assert parsed["revision"]["impact"] == "Less severe"
        assert "[REVISION]" not in parsed["display_text"]
        assert "[/REVISION]" not in parsed["display_text"]

    def test_extracts_preference(self):
        text = "Fair enough. [CONCEDED]\n[PREFERENCE: Author uses sentence fragments intentionally for voice]"
        parsed = parse_discussion_response(text)
        assert parsed["status"] == "conceded"
        assert parsed["preference"] == "Author uses sentence fragments intentionally for voice"
        assert "[PREFERENCE:" not in parsed["display_text"]

    def test_extracts_ambiguity_intentional(self):
        text = "Noted. [AMBIGUITY:INTENTIONAL] [CONTINUE]"
        parsed = parse_discussion_response(text)
        assert parsed["ambiguity"] == "intentional"
        assert "[AMBIGUITY:INTENTIONAL]" not in parsed["display_text"]

    def test_extracts_ambiguity_accidental(self):
        text = "Good to clarify. [AMBIGUITY:ACCIDENTAL] [CONTINUE]"
        parsed = parse_discussion_response(text)
        assert parsed["ambiguity"] == "accidental"

    def test_handles_malformed_revision_json(self):
        text = "Revised. [REVISED]\n[REVISION]\nnot valid json\n[/REVISION]"
        parsed = parse_discussion_response(text)
        assert parsed["status"] == "revised"
        assert parsed["revision"] is None  # Failed to parse

    def test_strips_all_tags_from_display(self):
        text = "Response. [AMBIGUITY:INTENTIONAL] [PREFERENCE: pref text] [REVISED]\n[REVISION]\n{\"severity\":\"minor\"}\n[/REVISION]"
        parsed = parse_discussion_response(text)
        assert "[" not in parsed["display_text"] or parsed["display_text"].strip() == "Response."


class TestApplyRevision:
    """Tests for apply_revision function."""

    def test_saves_old_version(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="old evidence",
                          impact="old impact", options=["old option"])
        apply_revision(finding, {"severity": "minor"})

        assert len(finding.revision_history) == 1
        assert finding.revision_history[0]["severity"] == "major"
        assert finding.revision_history[0]["evidence"] == "old evidence"

    def test_applies_severity_change(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="ev", impact="imp", options=["opt"])
        apply_revision(finding, {"severity": "minor"})
        assert finding.severity == "minor"

    def test_applies_evidence_change(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="old", impact="imp", options=["opt"])
        apply_revision(finding, {"evidence": "new evidence"})
        assert finding.evidence == "new evidence"

    def test_applies_impact_change(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="ev", impact="old", options=["opt"])
        apply_revision(finding, {"impact": "new impact"})
        assert finding.impact == "new impact"

    def test_applies_options_change(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="ev", impact="imp", options=["old"])
        apply_revision(finding, {"options": ["new1", "new2"]})
        assert finding.options == ["new1", "new2"]

    def test_partial_revision_only_changes_specified_fields(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="unchanged", impact="unchanged",
                          options=["unchanged"])
        apply_revision(finding, {"severity": "minor"})
        assert finding.severity == "minor"
        assert finding.evidence == "unchanged"
        assert finding.impact == "unchanged"

    def test_returns_old_version(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="ev", impact="imp", options=["opt"])
        old = apply_revision(finding, {"severity": "minor"})
        assert old["severity"] == "major"

    def test_multiple_revisions_accumulate_history(self):
        finding = Finding(number=1, severity="major", lens="prose",
                          location="P1", evidence="ev", impact="imp", options=["opt"])
        apply_revision(finding, {"severity": "minor"})
        apply_revision(finding, {"severity": "critical"})
        assert len(finding.revision_history) == 2
        assert finding.revision_history[0]["severity"] == "major"
        assert finding.revision_history[1]["severity"] == "minor"
        assert finding.severity == "critical"


class TestDescribeChanges:
    """Tests for _describe_changes helper."""

    def test_severity_change(self):
        desc = _describe_changes({"severity": "major"}, {"severity": "minor"})
        assert "major → minor" in desc

    def test_evidence_refined(self):
        desc = _describe_changes({"severity": "major"}, {"evidence": "new"})
        assert "evidence refined" in desc

    def test_no_changes(self):
        desc = _describe_changes({"severity": "major"}, {"severity": "major"})
        assert "minor refinements" in desc

    def test_multiple_changes(self):
        desc = _describe_changes(
            {"severity": "major"},
            {"severity": "minor", "impact": "new", "options": ["new"]}
        )
        assert "minor" in desc
        assert "impact" in desc
        assert "options" in desc


class TestBuildPriorOutcomesSummary:
    """Tests for build_prior_outcomes_summary (Phase 3)."""

    def test_empty_when_no_resolved_findings(self, sample_session_state, sample_finding):
        sample_session_state.findings = [sample_finding]  # status=pending
        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert result == ""

    def test_includes_accepted_finding(self, sample_session_state, sample_finding):
        other = Finding(number=2, severity="minor", lens="clarity",
                        location="P5", evidence="ev", impact="imp", options=["opt"])
        other.status = "accepted"
        other.outcome_reason = "Accepted by author"
        sample_session_state.findings = [other, sample_finding]

        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert "Finding #2" in result
        assert "ACCEPTED" in result

    def test_includes_rejected_finding(self, sample_session_state, sample_finding):
        other = Finding(number=2, severity="minor", lens="clarity",
                        location="P5", evidence="ev", impact="imp", options=["opt"])
        other.status = "rejected"
        other.outcome_reason = "Rejected by author: not an issue"
        sample_session_state.findings = [other, sample_finding]

        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert "REJECTED" in result
        assert "not an issue" in result

    def test_excludes_current_finding(self, sample_session_state, sample_finding):
        sample_finding.status = "accepted"
        sample_session_state.findings = [sample_finding]

        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert result == ""

    def test_excludes_pending_findings(self, sample_session_state, sample_finding):
        other = Finding(number=2, severity="minor", lens="clarity",
                        location="P5", evidence="ev", impact="imp", options=["opt"])
        other.status = "pending"
        sample_session_state.findings = [other, sample_finding]

        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert result == ""

    def test_includes_revised_finding(self, sample_session_state, sample_finding):
        other = Finding(number=2, severity="minor", lens="prose",
                        location="P3", evidence="ev", impact="imp", options=["opt"])
        other.status = "revised"
        other.outcome_reason = "Revised: severity major → minor"
        sample_session_state.findings = [other, sample_finding]

        result = build_prior_outcomes_summary(sample_session_state, sample_finding)
        assert "REVISED" in result


class TestHandleDiscussion:
    """Tests for handle_discussion (integration with mocked API)."""

    async def test_returns_tuple(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Good point. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        result = await handle_discussion(sample_session_state, sample_finding, "I disagree")
        assert isinstance(result, tuple)
        assert len(result) == 2

    async def test_uses_system_prompt(self, sample_session_state, sample_finding, mock_api_response):
        """Should call API with system parameter (multi-turn)."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Response. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "test")

        call_kwargs = sample_session_state.client.create_message.call_args
        assert "system" in call_kwargs.kwargs

    async def test_builds_multi_turn_messages(self, sample_session_state, sample_finding, mock_api_response):
        """Should pass proper message list with user/assistant turns."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("First response. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]

        await handle_discussion(sample_session_state, sample_finding, "First message")

        # Second turn should include prior turns
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Second response. [CONTINUE]")
        )
        await handle_discussion(sample_session_state, sample_finding, "Second message")

        call_kwargs = sample_session_state.client.create_message.call_args
        messages = call_kwargs.kwargs.get("messages", call_kwargs.args[0] if call_kwargs.args else [])
        # Should have: user1, assistant1, user2
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    async def test_stores_turns_on_finding(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Response. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Hello")

        assert len(sample_finding.discussion_turns) == 2
        assert sample_finding.discussion_turns[0]["role"] == "user"
        assert sample_finding.discussion_turns[0]["content"] == "Hello"
        assert sample_finding.discussion_turns[1]["role"] == "assistant"

    async def test_extracts_continue_status(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Let me explain further. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "Why?")
        assert status == "continue"
        assert "[CONTINUE]" not in response

    async def test_extracts_accepted_status(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Great, I'll note that fix. [ACCEPTED]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "I'll fix it")
        assert status == "accepted"
        assert "[ACCEPTED]" not in response

    async def test_extracts_rejected_status(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("I understand your position. [REJECTED]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "This is intentional")
        assert status == "rejected"

    async def test_extracts_conceded_status(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("You're right, my mistake. [CONCEDED]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "Check the context")
        assert status == "conceded"

    async def test_handles_revised_status_with_revision(self, sample_session_state, sample_finding, mock_api_response):
        """Phase 2: Revised finding should update severity."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response(
                'Fair point. [REVISED]\n[REVISION]\n{"severity": "minor"}\n[/REVISION]'
            )
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "It's not that bad")
        assert status == "revised"
        assert sample_finding.severity == "minor"
        assert len(sample_finding.revision_history) == 1

    async def test_handles_withdrawn_status(self, sample_session_state, sample_finding, mock_api_response):
        """Phase 2: Withdrawn finding."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("I was wrong about this. [WITHDRAWN]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "This isn't an issue")
        assert status == "withdrawn"
        assert "Withdrawn" in sample_finding.outcome_reason

    async def test_handles_escalated_status(self, sample_session_state, sample_finding, mock_api_response):
        """Phase 2: Escalated finding should increase severity."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response(
                'Actually this is worse. [ESCALATED]\n[REVISION]\n{"severity": "critical"}\n[/REVISION]'
            )
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "Wait, you're right")
        assert status == "escalated"
        assert sample_finding.severity == "critical"

    async def test_sets_outcome_reason_on_accept(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Glad you agree. [ACCEPTED]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Will fix")
        assert "Accepted" in sample_finding.outcome_reason

    async def test_sets_outcome_reason_on_reject(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("I see. [REJECTED]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Not a problem")
        assert "Rejected" in sample_finding.outcome_reason

    async def test_tracks_discussion_history(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Interesting point. [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        user_msg = "What about this?"
        await handle_discussion(sample_session_state, sample_finding, user_msg)

        assert len(sample_session_state.discussion_history) == 1
        assert sample_session_state.discussion_history[0]["user"] == user_msg
        assert sample_session_state.discussion_history[0]["finding_number"] == sample_finding.number

    async def test_tracks_rejection_for_learning(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Fair enough. [REJECTED]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Not an issue")

        assert len(sample_session_state.learning.session_rejections) == 1
        assert sample_session_state.learning.session_rejections[0]["lens"] == sample_finding.lens

    async def test_tracks_acceptance_for_learning(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Great! [ACCEPTED]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Will fix")

        assert len(sample_session_state.learning.session_acceptances) == 1

    async def test_tracks_preference_rule_in_learning(self, sample_session_state, sample_finding, mock_api_response):
        """Phase 4: Preference rules should be stored in rejection entries."""
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response(
                "Fair point. [CONCEDED]\n[PREFERENCE: Author uses fragments for voice]"
            )
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "It's my style")

        assert len(sample_session_state.learning.session_rejections) == 1
        assert sample_session_state.learning.session_rejections[0]["preference_rule"] == "Author uses fragments for voice"

    async def test_handles_ambiguity_intentional(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Noted. [AMBIGUITY:INTENTIONAL] [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "That's intentional")

        assert "[AMBIGUITY:INTENTIONAL]" not in response
        assert len(sample_session_state.learning.session_ambiguity_answers) == 1
        assert sample_session_state.learning.session_ambiguity_answers[0]["intentional"] is True

    async def test_handles_ambiguity_accidental(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("Good to clarify. [AMBIGUITY:ACCIDENTAL] [CONTINUE]")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "That's confusing")

        assert len(sample_session_state.learning.session_ambiguity_answers) == 1
        assert sample_session_state.learning.session_ambiguity_answers[0]["intentional"] is False

    async def test_handles_api_error(self, sample_session_state, sample_finding):
        sample_session_state.client.create_message = AsyncMock(
            side_effect=Exception("Network error")
        )
        sample_session_state.findings = [sample_finding]
        response, status = await handle_discussion(sample_session_state, sample_finding, "test")

        assert "error" in response.lower()
        assert status == "continue"

    async def test_conceded_tracks_as_rejection(self, sample_session_state, sample_finding, mock_api_response):
        sample_session_state.client.create_message = AsyncMock(
            return_value=mock_api_response("You're right. [CONCEDED]")
        )
        sample_session_state.findings = [sample_finding]
        await handle_discussion(sample_session_state, sample_finding, "Look at the context")

        assert len(sample_session_state.learning.session_rejections) == 1


class TestApplyDiscussionSideEffects:
    """Tests for _apply_discussion_side_effects (shared by both streaming and non-streaming)."""

    def test_stores_conversation_turns(self, sample_session_state, sample_finding):
        sample_session_state.findings = [sample_finding]
        parsed = {"display_text": "Response text", "status": "continue",
                  "revision": None, "preference": None, "ambiguity": None}
        _apply_discussion_side_effects(sample_session_state, sample_finding, "user msg", parsed)

        assert len(sample_finding.discussion_turns) == 2
        assert sample_finding.discussion_turns[0]["role"] == "user"
        assert sample_finding.discussion_turns[1]["role"] == "assistant"

    def test_appends_to_discussion_history(self, sample_session_state, sample_finding):
        sample_session_state.findings = [sample_finding]
        parsed = {"display_text": "Response", "status": "continue",
                  "revision": None, "preference": None, "ambiguity": None}
        _apply_discussion_side_effects(sample_session_state, sample_finding, "msg", parsed)

        assert len(sample_session_state.discussion_history) == 1

    def test_returns_response_and_status(self, sample_session_state, sample_finding):
        sample_session_state.findings = [sample_finding]
        parsed = {"display_text": "Clean response", "status": "accepted",
                  "revision": None, "preference": None, "ambiguity": None}
        response_text, status = _apply_discussion_side_effects(
            sample_session_state, sample_finding, "msg", parsed)

        assert response_text == "Clean response"
        assert status == "accepted"


class TestHandleDiscussionStream:
    """Tests for handle_discussion_stream (streaming variant)."""

    async def test_yields_token_chunks(self, sample_session_state, sample_finding, mock_streaming_response):
        """Should yield token chunks before the done event."""
        chunks = ["Good ", "point. ", "[CONTINUE]"]
        full_text = "Good point. [CONTINUE]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text, chunks)
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "I disagree"):
            events.append(event)

        # Should have token events + done event
        token_events = [e for e in events if e[0] == "token"]
        done_events = [e for e in events if e[0] == "done"]

        assert len(token_events) == 3
        assert token_events[0] == ("token", "Good ")
        assert token_events[1] == ("token", "point. ")
        assert token_events[2] == ("token", "[CONTINUE]")
        assert len(done_events) == 1

    async def test_done_event_contains_parsed_response(self, sample_session_state, sample_finding, mock_streaming_response):
        """Done event should contain cleaned display text and status."""
        full_text = "Let me explain further. [CONTINUE]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "Why?"):
            events.append(event)

        done = [e for e in events if e[0] == "done"][0]
        result = done[1]
        assert result["status"] == "continue"
        assert "[CONTINUE]" not in result["response"]
        assert "explain further" in result["response"]

    async def test_applies_side_effects_on_accept(self, sample_session_state, sample_finding, mock_streaming_response):
        """Side effects should be applied after stream completes."""
        full_text = "Great, noted. [ACCEPTED]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        async for _ in handle_discussion_stream(sample_session_state, sample_finding, "I'll fix it"):
            pass

        assert "Accepted" in sample_finding.outcome_reason
        assert len(sample_session_state.learning.session_acceptances) == 1
        assert len(sample_finding.discussion_turns) == 2

    async def test_applies_side_effects_on_reject(self, sample_session_state, sample_finding, mock_streaming_response):
        full_text = "Fair enough. [REJECTED]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        async for _ in handle_discussion_stream(sample_session_state, sample_finding, "Not an issue"):
            pass

        assert "Rejected" in sample_finding.outcome_reason
        assert len(sample_session_state.learning.session_rejections) == 1

    async def test_applies_revision(self, sample_session_state, sample_finding, mock_streaming_response):
        """Phase 2: Revision should be applied after stream completes."""
        full_text = 'Fair point. [REVISED]\n[REVISION]\n{"severity": "minor"}\n[/REVISION]'
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "Too harsh"):
            events.append(event)

        done = [e for e in events if e[0] == "done"][0]
        assert done[1]["status"] == "revised"
        assert sample_finding.severity == "minor"
        assert len(sample_finding.revision_history) == 1

    async def test_handles_withdrawn(self, sample_session_state, sample_finding, mock_streaming_response):
        full_text = "I was wrong about this. [WITHDRAWN]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "Not an issue"):
            events.append(event)

        done = [e for e in events if e[0] == "done"][0]
        assert done[1]["status"] == "withdrawn"
        assert "Withdrawn" in sample_finding.outcome_reason

    async def test_handles_escalated(self, sample_session_state, sample_finding, mock_streaming_response):
        full_text = 'Actually worse. [ESCALATED]\n[REVISION]\n{"severity": "critical"}\n[/REVISION]'
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "You're right"):
            events.append(event)

        done = [e for e in events if e[0] == "done"][0]
        assert done[1]["status"] == "escalated"
        assert sample_finding.severity == "critical"

    async def test_handles_preference_extraction(self, sample_session_state, sample_finding, mock_streaming_response):
        full_text = "Fair point. [CONCEDED]\n[PREFERENCE: Author uses fragments for voice]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        async for _ in handle_discussion_stream(sample_session_state, sample_finding, "It's my style"):
            pass

        assert len(sample_session_state.learning.session_rejections) == 1
        assert sample_session_state.learning.session_rejections[0]["preference_rule"] == "Author uses fragments for voice"

    async def test_handles_api_error(self, sample_session_state, sample_finding):
        """API errors should yield a done event with error message."""
        async def _error_stream(**kwargs):
            raise Exception("Network error")
            yield  # makes this an async generator
        sample_session_state.client.stream_message = _error_stream
        sample_session_state.findings = [sample_finding]

        events = []
        async for event in handle_discussion_stream(sample_session_state, sample_finding, "test"):
            events.append(event)

        assert len(events) == 1
        assert events[0][0] == "done"
        assert "error" in events[0][1]["response"].lower()
        assert events[0][1]["status"] == "continue"

    async def test_stores_conversation_turns(self, sample_session_state, sample_finding, mock_streaming_response):
        """Should store turns on the finding after streaming."""
        full_text = "Response. [CONTINUE]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        async for _ in handle_discussion_stream(sample_session_state, sample_finding, "Hello"):
            pass

        assert len(sample_finding.discussion_turns) == 2
        assert sample_finding.discussion_turns[0]["role"] == "user"
        assert sample_finding.discussion_turns[0]["content"] == "Hello"
        assert sample_finding.discussion_turns[1]["role"] == "assistant"

    async def test_tracks_discussion_history(self, sample_session_state, sample_finding, mock_streaming_response):
        full_text = "Interesting. [CONTINUE]"
        sample_session_state.client.stream_message = mock_streaming_response(full_text)
        sample_session_state.findings = [sample_finding]

        async for _ in handle_discussion_stream(sample_session_state, sample_finding, "What about this?"):
            pass

        assert len(sample_session_state.discussion_history) == 1
        assert sample_session_state.discussion_history[0]["user"] == "What about this?"
