"""
Tests for learning data management functions (Phase 2).

Tests load_learning(), export_learning_markdown(), LearningStore operations.
"""

import pytest
from pathlib import Path
from lit_platform.runtime.learning import load_learning, export_learning_markdown
from lit_platform.runtime.db import get_connection, LearningStore
from lit_platform.runtime.models import LearningData


class TestLoadLearning:
    """Tests for load_learning function."""

    def test_returns_empty_structure_for_new_project(self, temp_project_dir):
        """A new project should have empty learning data."""
        learning = load_learning(temp_project_dir)
        
        assert isinstance(learning, LearningData)
        assert learning.preferences == []
        assert learning.blind_spots == []
        assert learning.resolutions == []
        assert learning.ambiguity_intentional == []
        assert learning.ambiguity_accidental == []
        assert learning.review_count == 0

    def test_loads_all_categories(self, temp_project_dir):
        """Should load all learning categories with data."""
        conn = get_connection(temp_project_dir)
        try:
            # Add learning entries
            LearningStore.add_preference(conn, "[prose] Sentence fragments OK for voice")
            LearningStore.add_blind_spot(conn, "[clarity] Pronoun ambiguity in dialogue")
            LearningStore.add_resolution(conn, "Finding #5 — addressed by splitting paragraph")
            LearningStore.add_ambiguity(conn, "Chapter 3: dream sequence", intentional=True)
            LearningStore.add_ambiguity(conn, "Chapter 5: unclear referent", intentional=False)
            LearningStore.increment_review_count(conn)
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        
        assert len(learning.preferences) == 1
        assert len(learning.blind_spots) == 1
        assert len(learning.resolutions) == 1
        assert len(learning.ambiguity_intentional) == 1
        assert len(learning.ambiguity_accidental) == 1
        assert learning.review_count == 1

    def test_includes_entry_ids_for_deletion(self, temp_project_dir):
        """Learning entries should include IDs for deletion."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test preference 1")
            LearningStore.add_preference(conn, "Test preference 2")
            LearningStore.add_blind_spot(conn, "Test blind spot")
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        
        # Preferences should have IDs
        assert all('id' in entry for entry in learning.preferences)
        assert all('description' in entry for entry in learning.preferences)
        
        # IDs should be unique and positive
        pref_ids = [entry['id'] for entry in learning.preferences]
        assert len(pref_ids) == len(set(pref_ids))  # No duplicates
        assert all(id > 0 for id in pref_ids)

    def test_preserves_entry_order(self, temp_project_dir):
        """Entries should be returned in insertion order."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "First preference")
            LearningStore.add_preference(conn, "Second preference")
            LearningStore.add_preference(conn, "Third preference")
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        
        assert learning.preferences[0]['description'] == "First preference"
        assert learning.preferences[1]['description'] == "Second preference"
        assert learning.preferences[2]['description'] == "Third preference"


class TestExportLearningMarkdown:
    """Tests for export_learning_markdown function."""

    def test_creates_learning_md_file(self, temp_project_dir):
        """Should create LEARNING.md in the project directory."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test preference")
            LearningStore.increment_review_count(conn)
        finally:
            conn.close()

        filepath = export_learning_markdown(temp_project_dir)
        
        assert filepath == temp_project_dir / "LEARNING.md"
        assert filepath.exists()

    def test_includes_all_categories(self, temp_project_dir):
        """Exported file should include all learning categories."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "[prose] Test preference")
            LearningStore.add_blind_spot(conn, "[clarity] Test blind spot")
            LearningStore.add_resolution(conn, "Finding #1 — resolved by edit")
            LearningStore.add_ambiguity(conn, "Dream sequence", intentional=True)
            LearningStore.add_ambiguity(conn, "Unclear pronoun", intentional=False)
            LearningStore.increment_review_count(conn)
        finally:
            conn.close()

        filepath = export_learning_markdown(temp_project_dir)
        content = filepath.read_text(encoding='utf-8')
        
        assert "# Learning" in content
        assert "## Preferences" in content
        assert "## Blind Spots" in content
        assert "## Resolutions" in content
        assert "## Ambiguity Patterns" in content
        assert "### Intentional" in content
        assert "### Accidental" in content
        assert "[prose] Test preference" in content
        assert "[clarity] Test blind spot" in content

    def test_includes_review_count(self, temp_project_dir):
        """Exported file should include review count."""
        conn = get_connection(temp_project_dir)
        try:
            for _ in range(3):
                LearningStore.increment_review_count(conn)
        finally:
            conn.close()

        filepath = export_learning_markdown(temp_project_dir)
        content = filepath.read_text(encoding='utf-8')
        
        assert "REVIEW_COUNT: 3" in content

    def test_handles_empty_learning_data(self, temp_project_dir):
        """Should handle exporting empty learning data gracefully."""
        filepath = export_learning_markdown(temp_project_dir)
        
        assert filepath.exists()
        content = filepath.read_text(encoding='utf-8')
        assert "# Learning" in content
        assert "REVIEW_COUNT: 0" in content


class TestLearningStoreReset:
    """Tests for LearningStore.reset() operation."""

    def test_clears_all_learning_data(self, temp_project_dir):
        """Reset should clear all learning entries."""
        conn = get_connection(temp_project_dir)
        try:
            # Add various learning entries
            LearningStore.add_preference(conn, "Pref 1")
            LearningStore.add_preference(conn, "Pref 2")
            LearningStore.add_blind_spot(conn, "Blind spot")
            LearningStore.add_resolution(conn, "Resolution")
            LearningStore.add_ambiguity(conn, "Intentional", intentional=True)
            LearningStore.add_ambiguity(conn, "Accidental", intentional=False)
            for _ in range(5):
                LearningStore.increment_review_count(conn)

            # Reset
            LearningStore.reset(conn)
        finally:
            conn.close()

        # Verify all data is gone
        learning = load_learning(temp_project_dir)
        assert learning.preferences == []
        assert learning.blind_spots == []
        assert learning.resolutions == []
        assert learning.ambiguity_intentional == []
        assert learning.ambiguity_accidental == []
        assert learning.review_count == 0

    def test_preserves_schema(self, temp_project_dir):
        """Reset should preserve table schema, just empty data."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test")
            LearningStore.reset(conn)
            
            # Should be able to add new entries after reset
            LearningStore.add_preference(conn, "New preference after reset")
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        assert len(learning.preferences) == 1
        assert learning.preferences[0]['description'] == "New preference after reset"

    def test_reset_multiple_times(self, temp_project_dir):
        """Should be able to reset multiple times without error."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Test 1")
            LearningStore.reset(conn)
            
            LearningStore.add_preference(conn, "Test 2")
            LearningStore.reset(conn)
            
            LearningStore.add_preference(conn, "Test 3")
            LearningStore.reset(conn)
        finally:
            conn.close()

        learning = load_learning(temp_project_dir)
        assert learning.preferences == []


class TestLearningStoreRemoveEntry:
    """Tests for LearningStore.remove_entry() operation."""

    def test_removes_entry_and_returns_true(self, temp_project_dir):
        """Should remove specific entry and return True."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Preference 1")
            LearningStore.add_preference(conn, "Preference 2")
        finally:
            conn.close()

        learning_before = load_learning(temp_project_dir)
        assert len(learning_before.preferences) == 2
        entry_id = learning_before.preferences[0]['id']

        conn = get_connection(temp_project_dir)
        try:
            result = LearningStore.remove_entry(conn, entry_id)
            assert result is True
        finally:
            conn.close()

        learning_after = load_learning(temp_project_dir)
        assert len(learning_after.preferences) == 1
        assert learning_after.preferences[0]['description'] == "Preference 2"

    def test_returns_false_for_nonexistent_entry(self, temp_project_dir):
        """Should return False when entry doesn't exist."""
        conn = get_connection(temp_project_dir)
        try:
            result = LearningStore.remove_entry(conn, 9999)
            assert result is False
        finally:
            conn.close()

    def test_removes_from_correct_category(self, temp_project_dir):
        """Should remove entry from the correct category only."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_preference(conn, "Preference")
            LearningStore.add_blind_spot(conn, "Blind spot 1")
            LearningStore.add_blind_spot(conn, "Blind spot 2")
        finally:
            conn.close()

        learning_before = load_learning(temp_project_dir)
        blind_spot_id = learning_before.blind_spots[0]['id']

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.remove_entry(conn, blind_spot_id)
        finally:
            conn.close()

        learning_after = load_learning(temp_project_dir)
        
        # Preference should be untouched
        assert len(learning_after.preferences) == 1
        assert learning_after.preferences[0]['description'] == "Preference"
        
        # One blind spot should be removed
        assert len(learning_after.blind_spots) == 1
        assert learning_after.blind_spots[0]['description'] == "Blind spot 2"

    def test_handles_ambiguity_entries(self, temp_project_dir):
        """Should correctly remove ambiguity entries (both types)."""
        conn = get_connection(temp_project_dir)
        try:
            LearningStore.add_ambiguity(conn, "Intentional 1", intentional=True)
            LearningStore.add_ambiguity(conn, "Intentional 2", intentional=True)
            LearningStore.add_ambiguity(conn, "Accidental 1", intentional=False)
        finally:
            conn.close()

        learning_before = load_learning(temp_project_dir)
        intentional_id = learning_before.ambiguity_intentional[0]['id']

        conn = get_connection(temp_project_dir)
        try:
            LearningStore.remove_entry(conn, intentional_id)
        finally:
            conn.close()

        learning_after = load_learning(temp_project_dir)
        
        # One intentional should be removed
        assert len(learning_after.ambiguity_intentional) == 1
        assert learning_after.ambiguity_intentional[0]['description'] == "Intentional 2"
        
        # Accidental should be untouched
        assert len(learning_after.ambiguity_accidental) == 1
