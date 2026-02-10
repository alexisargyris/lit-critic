"""
Tests for lit-critic.learning module.
"""

import pytest
from pathlib import Path
from server.learning import (
    load_learning,
    generate_learning_markdown,
    save_learning_to_file,
    update_learning_from_session,
)
from server.models import LearningData


class TestLoadLearning:
    """Tests for load_learning function."""
    
    def test_returns_learning_data(self, tmp_path):
        """Should return a LearningData object."""
        result = load_learning(tmp_path)
        assert isinstance(result, LearningData)
    
    def test_empty_when_no_file(self, tmp_path):
        """Should return empty learning data when file doesn't exist."""
        result = load_learning(tmp_path)
        
        assert result.project_name == "Unknown"
        assert result.review_count == 0
        assert result.preferences == []
    
    def test_parses_project_name(self, tmp_path):
        """Should parse PROJECT field."""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text("PROJECT: My Great Novel\n", encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert result.project_name == "My Great Novel"
    
    def test_parses_review_count(self, tmp_path):
        """Should parse REVIEW_COUNT field."""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text("REVIEW_COUNT: 42\n", encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert result.review_count == 42
    
    def test_parses_preferences(self, tmp_path):
        """Should parse preferences section."""
        content = """## Preferences

- [prose] Sentence fragments are intentional
- [structure] Short chapters are intentional
"""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text(content, encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert len(result.preferences) == 2
        assert "Sentence fragments" in result.preferences[0]["description"]
    
    def test_parses_blind_spots(self, tmp_path):
        """Should parse blind spots section."""
        content = """## Blind Spots

- [clarity] Often misses pronoun ambiguity
"""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text(content, encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert len(result.blind_spots) == 1
        assert "pronoun" in result.blind_spots[0]["description"]
    
    def test_parses_ambiguity_patterns(self, tmp_path):
        """Should parse ambiguity patterns sections."""
        content = """## Ambiguity Patterns

### Intentional

- Dream sequences are deliberately unclear

### Accidental

- Time jumps sometimes confusing
"""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text(content, encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert len(result.ambiguity_intentional) == 1
        assert "Dream" in result.ambiguity_intentional[0]["description"]
        assert len(result.ambiguity_accidental) == 1
        assert "Time" in result.ambiguity_accidental[0]["description"]
    
    def test_handles_invalid_review_count(self, tmp_path):
        """Should handle non-numeric review count gracefully."""
        learning_file = tmp_path / "LEARNING.md"
        learning_file.write_text("REVIEW_COUNT: not-a-number\n", encoding='utf-8')
        
        result = load_learning(tmp_path)
        assert result.review_count == 0  # Default value


class TestGenerateLearningMarkdown:
    """Tests for generate_learning_markdown function."""
    
    def test_includes_header(self):
        """Generated markdown should include header."""
        learning = LearningData()
        result = generate_learning_markdown(learning)
        assert "# Learning" in result
    
    def test_includes_project_name(self):
        """Generated markdown should include project name."""
        learning = LearningData(project_name="Test Project")
        result = generate_learning_markdown(learning)
        assert "PROJECT: Test Project" in result
    
    def test_includes_review_count(self):
        """Generated markdown should include review count."""
        learning = LearningData(review_count=5)
        result = generate_learning_markdown(learning)
        assert "REVIEW_COUNT: 5" in result
    
    def test_includes_last_updated(self):
        """Generated markdown should include LAST_UPDATED."""
        learning = LearningData()
        result = generate_learning_markdown(learning)
        assert "LAST_UPDATED:" in result
    
    def test_includes_sections(self):
        """Generated markdown should include all sections."""
        learning = LearningData()
        result = generate_learning_markdown(learning)
        
        assert "## Preferences" in result
        assert "## Blind Spots" in result
        assert "## Resolutions" in result
        assert "## Ambiguity Patterns" in result
        assert "### Intentional" in result
        assert "### Accidental" in result
    
    def test_empty_sections_show_placeholder(self):
        """Empty sections should show placeholder."""
        learning = LearningData()
        result = generate_learning_markdown(learning)
        assert "[none yet]" in result
    
    def test_includes_preferences(self):
        """Generated markdown should include preference items."""
        learning = LearningData()
        learning.preferences.append({"description": "Test preference"})
        
        result = generate_learning_markdown(learning)
        assert "- Test preference" in result
    
    def test_includes_blind_spots(self):
        """Generated markdown should include blind spot items."""
        learning = LearningData()
        learning.blind_spots.append({"description": "Test blind spot"})
        
        result = generate_learning_markdown(learning)
        assert "- Test blind spot" in result


class TestSaveLearningToFile:
    """Tests for save_learning_to_file function."""
    
    def test_creates_file(self, tmp_path):
        """Should create LEARNING.md file."""
        learning = LearningData(project_name="Test")
        filepath = save_learning_to_file(learning, tmp_path)
        
        assert filepath.exists()
        assert filepath.name == "LEARNING.md"
    
    def test_returns_path(self, tmp_path):
        """Should return the file path."""
        learning = LearningData()
        result = save_learning_to_file(learning, tmp_path)
        
        assert isinstance(result, Path)
    
    def test_file_contains_content(self, tmp_path):
        """Saved file should contain learning data."""
        learning = LearningData(project_name="My Novel", review_count=3)
        filepath = save_learning_to_file(learning, tmp_path)
        
        content = filepath.read_text(encoding='utf-8')
        assert "My Novel" in content
    
    def test_overwrites_existing(self, tmp_path):
        """Should overwrite existing file."""
        # Write initial file
        learning1 = LearningData(project_name="First")
        save_learning_to_file(learning1, tmp_path)
        
        # Write new file
        learning2 = LearningData(project_name="Second")
        filepath = save_learning_to_file(learning2, tmp_path)
        
        content = filepath.read_text(encoding='utf-8')
        assert "Second" in content
        assert "First" not in content


class TestUpdateLearningFromSession:
    """Tests for update_learning_from_session function."""
    
    def test_increments_review_count(self):
        """Should increment review count."""
        learning = LearningData(review_count=5)
        update_learning_from_session(learning)
        assert learning.review_count == 6
    
    def test_processes_rejections_to_preferences(self):
        """Session rejections should become preferences."""
        learning = LearningData()
        learning.session_rejections.append({
            "lens": "prose",
            "pattern": "sentence fragment style",
            "reason": "intentional for voice"
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.preferences) == 1
        assert "[prose]" in learning.preferences[0]["description"]
        assert "sentence fragment" in learning.preferences[0]["description"]
    
    def test_does_not_duplicate_preferences(self):
        """Should not add duplicate preferences."""
        learning = LearningData()
        learning.preferences.append({
            "description": "[prose] sentence fragment style — Author says: \"intentional\""
        })
        learning.session_rejections.append({
            "lens": "prose",
            "pattern": "sentence fragment style",
            "reason": "intentional"
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.preferences) == 1  # No duplicate added
    
    def test_preference_rule_used_when_available(self):
        """Phase 4: Should use explicit preference_rule from discussion when available."""
        learning = LearningData()
        learning.session_rejections.append({
            "lens": "prose",
            "pattern": "sentence fragment style",
            "reason": "intentional for voice",
            "preference_rule": "Sentence fragments are an intentional stylistic choice for narrative voice"
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.preferences) == 1
        desc = learning.preferences[0]["description"]
        assert "[prose]" in desc
        assert "Sentence fragments are an intentional stylistic choice" in desc
        # Should NOT contain the old format with "Author says:"
        assert "Author says:" not in desc
    
    def test_preference_rule_fallback_when_absent(self):
        """Phase 4: Should fall back to original format when preference_rule is absent."""
        learning = LearningData()
        learning.session_rejections.append({
            "lens": "clarity",
            "pattern": "ambiguous referent",
            "reason": "it's clear from context"
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.preferences) == 1
        desc = learning.preferences[0]["description"]
        assert "[clarity]" in desc
        assert "Author says:" in desc
        assert "it's clear from context" in desc
    
    def test_preference_rule_empty_string_falls_back(self):
        """Phase 4: Empty preference_rule string should fall back to original format."""
        learning = LearningData()
        learning.session_rejections.append({
            "lens": "logic",
            "pattern": "motivation gap",
            "reason": "implied by earlier scene",
            "preference_rule": ""
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.preferences) == 1
        desc = learning.preferences[0]["description"]
        # Empty preference_rule is falsy, should use fallback
        assert "Author says:" in desc
    
    def test_processes_intentional_ambiguity(self):
        """Intentional ambiguity answers should be recorded."""
        learning = LearningData()
        learning.session_ambiguity_answers.append({
            "location": "Chapter 3, paragraph 5",
            "description": "Dream imagery",
            "intentional": True
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.ambiguity_intentional) == 1
        assert "Chapter 3" in learning.ambiguity_intentional[0]["description"]
    
    def test_processes_accidental_ambiguity(self):
        """Accidental ambiguity answers should be recorded."""
        learning = LearningData()
        learning.session_ambiguity_answers.append({
            "location": "Page 42",
            "description": "Unclear referent",
            "intentional": False
        })
        
        update_learning_from_session(learning)
        
        assert len(learning.ambiguity_accidental) == 1
        assert "Page 42" in learning.ambiguity_accidental[0]["description"]


class TestRoundtrip:
    """Integration tests for save/load roundtrip."""
    
    def test_full_roundtrip(self, tmp_path):
        """Save and load should preserve all data."""
        original = LearningData(
            project_name="Roundtrip Test",
            review_count=10,
        )
        original.preferences.append({"description": "Pref 1"})
        original.blind_spots.append({"description": "Blind 1"})
        original.resolutions.append({"description": "Res 1"})
        original.ambiguity_intentional.append({"description": "Intent 1"})
        original.ambiguity_accidental.append({"description": "Accident 1"})
        
        initial_review_count = original.review_count
        save_learning_to_file(original, tmp_path)
        loaded = load_learning(tmp_path)
        
        assert loaded.project_name == original.project_name
        # Note: review_count is incremented during save (mutates original)
        assert loaded.review_count == initial_review_count + 1
        assert original.review_count == initial_review_count + 1  # Original is mutated
        assert len(loaded.preferences) == 1
        assert len(loaded.blind_spots) == 1
        assert len(loaded.ambiguity_intentional) == 1
        assert len(loaded.ambiguity_accidental) == 1
