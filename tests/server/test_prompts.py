"""
Tests for lit-critic.prompts module.
"""

import pytest
from lit_platform.runtime.prompts import (
    get_lens_prompt,
    get_coordinator_prompt,
    get_discussion_system_prompt,
    build_discussion_messages,
)
from lit_platform.runtime.models import Finding, LensResult


class TestGetLensPrompt:
    """Tests for get_lens_prompt function."""
    
    def test_prose_lens_prompt(self, sample_indexes):
        """Prose lens prompt should include relevant instructions."""
        prompt = get_lens_prompt("prose", "Test scene content", sample_indexes)
        
        assert "PROSE" in prompt
        assert "sentence-level" in prompt.lower() or "paragraph-level" in prompt.lower()
        assert "rhythm" in prompt.lower()
        assert "JSON" in prompt
    
    def test_structure_lens_prompt(self, sample_indexes):
        """Structure lens prompt should include relevant instructions."""
        prompt = get_lens_prompt("structure", "Test scene content", sample_indexes)
        
        assert "STRUCTURE" in prompt
        assert "scene" in prompt.lower()
        assert "pacing" in prompt.lower() or "objective" in prompt.lower()
    
    def test_logic_lens_prompt(self, sample_indexes):
        """Logic lens prompt should include relevant instructions."""
        prompt = get_lens_prompt("logic", "Test scene content", sample_indexes)
        
        assert "LOGIC" in prompt
        assert "motivation" in prompt.lower() or "action" in prompt.lower()
        assert "CAST.md" in prompt or "CANON.md" in prompt
    
    def test_clarity_lens_prompt(self, sample_indexes):
        """Clarity lens prompt should include relevant instructions."""
        prompt = get_lens_prompt("clarity", "Test scene content", sample_indexes)
        
        assert "CLARITY" in prompt
        assert "referent" in prompt.lower() or "pronoun" in prompt.lower()
        assert "ambiguity" in prompt.lower()
    
    def test_continuity_lens_prompt(self, sample_indexes):
        """Continuity lens prompt should include relevant instructions."""
        prompt = get_lens_prompt("continuity", "Test scene content", sample_indexes)
        
        assert "CONTINUITY" in prompt
        assert "GLOSSARY" in prompt
        assert "glossary_issues" in prompt
    
    def test_includes_all_indexes(self, sample_indexes):
        """Prompt should include all provided index content."""
        prompt = get_lens_prompt("prose", "Test scene", sample_indexes)
        
        assert "Magic system uses crystals" in prompt  # From CANON.md
        assert "Elena" in prompt  # From CAST.md
        assert "Lumina" in prompt  # From GLOSSARY.md
    
    def test_includes_scene(self, sample_indexes, sample_scene):
        """Prompt should include the scene content."""
        prompt = get_lens_prompt("prose", sample_scene, sample_indexes)
        
        assert "Elena walked through" in prompt
    
    def test_includes_learning_reference(self, sample_indexes):
        """Prompt should reference LEARNING.md."""
        prompt = get_lens_prompt("prose", "Test scene", sample_indexes)
        
        assert "LEARNING.md" in prompt or "learning" in prompt.lower()
    
    def test_missing_index_shows_placeholder(self):
        """Missing index files should show placeholder text."""
        sparse_indexes = {"CANON.md": "Some content"}
        prompt = get_lens_prompt("prose", "Test scene", sparse_indexes)
        
        assert "[Not provided]" in prompt


class TestGetCoordinatorPrompt:
    """Tests for get_coordinator_prompt function."""
    
    def test_includes_lens_results(self, sample_lens_results, sample_scene):
        """Coordinator prompt should include all lens outputs."""
        prompt = get_coordinator_prompt(sample_lens_results, sample_scene)
        
        assert "PROSE LENS OUTPUT" in prompt
        assert "STRUCTURE LENS OUTPUT" in prompt
        assert "LOGIC LENS OUTPUT" in prompt
        assert "CLARITY LENS OUTPUT" in prompt
        assert "CONTINUITY LENS OUTPUT" in prompt
    
    def test_includes_raw_output(self, sample_lens_results, sample_scene):
        """Coordinator prompt should include raw outputs from lenses."""
        prompt = get_coordinator_prompt(sample_lens_results, sample_scene)
        
        assert "Repetitive sentence starts" in prompt
        assert "Unclear referent" in prompt
    
    def test_requests_tool_use(self, sample_lens_results, sample_scene):
        """Coordinator prompt should instruct the model to use the report_findings tool."""
        prompt = get_coordinator_prompt(sample_lens_results, sample_scene)

        assert "report_findings" in prompt
    
    def test_mentions_deduplication(self, sample_lens_results, sample_scene):
        """Coordinator prompt should mention deduplication."""
        prompt = get_coordinator_prompt(sample_lens_results, sample_scene)
        
        assert "deduplicate" in prompt.lower() or "merge" in prompt.lower()


class TestGetDiscussionSystemPrompt:
    """Tests for get_discussion_system_prompt (Phase 1: multi-turn system prompt)."""

    def test_includes_finding_details(self, sample_finding):
        """System prompt should include finding details."""
        prompt = get_discussion_system_prompt(sample_finding, "Scene text here")

        assert str(sample_finding.number) in prompt
        assert sample_finding.severity in prompt
        assert sample_finding.lens in prompt
        assert sample_finding.location in prompt
        assert sample_finding.evidence in prompt

    def test_includes_full_scene(self, sample_finding, sample_scene):
        """System prompt should include full scene text (not truncated)."""
        prompt = get_discussion_system_prompt(sample_finding, sample_scene)

        assert "Elena walked through" in prompt
        assert "I need to find another way" in prompt  # Near end of scene

    def test_includes_status_markers(self, sample_finding):
        """System prompt should mention all status markers."""
        prompt = get_discussion_system_prompt(sample_finding, "Scene text")

        assert "[REJECTED]" in prompt
        assert "[ACCEPTED]" in prompt
        assert "[CONCEDED]" in prompt
        assert "[REVISED]" in prompt
        assert "[WITHDRAWN]" in prompt
        assert "[ESCALATED]" in prompt

    def test_includes_revision_format(self, sample_finding):
        """System prompt should describe the revision block format."""
        prompt = get_discussion_system_prompt(sample_finding, "Scene text")

        assert "[REVISION]" in prompt
        assert "[/REVISION]" in prompt

    def test_includes_preference_format(self, sample_finding):
        """System prompt should describe the preference tag format."""
        prompt = get_discussion_system_prompt(sample_finding, "Scene text")

        assert "[PREFERENCE:" in prompt

    def test_includes_prior_outcomes(self, sample_finding):
        """System prompt should include prior outcomes when provided."""
        prior = "- Finding #1 (prose, major): REJECTED — author says intentional"
        prompt = get_discussion_system_prompt(sample_finding, "Scene text", prior_outcomes=prior)

        assert "Finding #1" in prompt
        assert "REJECTED" in prompt
        assert "PRIOR DISCUSSION OUTCOMES" in prompt

    def test_no_prior_outcomes_section_when_empty(self, sample_finding):
        """System prompt should not include prior outcomes section when empty."""
        prompt = get_discussion_system_prompt(sample_finding, "Scene text", prior_outcomes="")

        assert "PRIOR DISCUSSION OUTCOMES" not in prompt

    def test_uses_canonical_line_range_in_location_when_location_contains_stale_l_range(self):
        """Location text should be normalized from canonical numeric line fields."""
        finding = Finding(
            number=1,
            severity="major",
            lens="prose",
            location="L120-L124, starting 'She moved...'",
            line_start=12,
            line_end=16,
            evidence="Test evidence",
            impact="Test impact",
            options=["Test option"],
        )

        prompt = get_discussion_system_prompt(finding, "Scene text")
        assert "Location: L12-L16, starting 'She moved...'" in prompt
        assert "Line range: L12-L16" in prompt

    def test_uses_canonical_line_range_even_when_location_has_no_l_range(self):
        """Line range display should always be derived from numeric line fields."""
        finding = Finding(
            number=1,
            severity="major",
            lens="prose",
            location="Paragraph 3 near midpoint",
            line_start=8,
            line_end=10,
            evidence="Test evidence",
            impact="Test impact",
            options=["Test option"],
        )

        prompt = get_discussion_system_prompt(finding, "Scene text")
        assert "Location: Paragraph 3 near midpoint" in prompt
        assert "Line range: L8-L10" in prompt


class TestBuildDiscussionMessages:
    """Tests for build_discussion_messages (Phase 1: proper message list)."""

    def test_single_message(self, sample_finding):
        """First message should produce a single-element list."""
        messages = build_discussion_messages(sample_finding, "I disagree")

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "I disagree"

    def test_includes_prior_turns(self, sample_finding):
        """Should include prior discussion turns from finding."""
        sample_finding.discussion_turns = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First response"},
        ]
        messages = build_discussion_messages(sample_finding, "Follow up")

        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "First message"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "First response"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Follow up"

    def test_empty_turns_produces_single_message(self, sample_finding):
        """Finding with no prior turns should produce just the new message."""
        sample_finding.discussion_turns = []
        messages = build_discussion_messages(sample_finding, "Hello")

        assert len(messages) == 1
        assert messages[0]["content"] == "Hello"
