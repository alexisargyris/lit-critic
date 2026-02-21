"""
Tests for the server.learning module (SQLite-backed).
"""

import pytest
from pathlib import Path
from lit_platform.runtime.learning import (
    load_learning,
    load_learning_from_db,
    persist_learning,
    generate_learning_markdown,
    export_learning_markdown,
    save_learning_to_file,
    update_learning_from_session,
)
from lit_platform.runtime.db import get_connection, LearningStore
from lit_platform.runtime.models import LearningData


class TestLoadLearning:
    def test_returns_learning_data(self, temp_project_dir):
        result = load_learning(temp_project_dir)
        assert isinstance(result, LearningData)

    def test_empty_when_no_data(self, temp_project_dir):
        result = load_learning(temp_project_dir)
        assert result.project_name == "Unknown"
        assert result.review_count == 0

    def test_imports_from_markdown(self, temp_project_dir):
        """First load imports existing LEARNING.md into DB."""
        md = "PROJECT: Test Novel\nREVIEW_COUNT: 5\n\n## Preferences\n\n- [prose] Test pref\n"
        (temp_project_dir / "LEARNING.md").write_text(md, encoding='utf-8')

        result = load_learning(temp_project_dir)
        assert result.project_name == "Test Novel"
        assert result.review_count == 5
        assert len(result.preferences) == 1

    def test_db_takes_priority_over_markdown(self, temp_project_dir):
        """Once imported, DB data wins even if LEARNING.md is still there."""
        md = "PROJECT: Old Name\nREVIEW_COUNT: 1\n"
        (temp_project_dir / "LEARNING.md").write_text(md, encoding='utf-8')

        # First load imports
        load_learning(temp_project_dir)

        # Update DB directly
        conn = get_connection(temp_project_dir)
        try:
            conn.execute("UPDATE learning SET project_name = 'New Name', review_count = 10")
            conn.commit()
        finally:
            conn.close()

        # Second load uses DB
        result = load_learning(temp_project_dir)
        assert result.project_name == "New Name"
        assert result.review_count == 10


class TestLoadLearningFromDb:
    def test_loads_from_connection(self, db_conn):
        ld = LearningData(project_name="Test", review_count=3)
        ld.preferences.append({"description": "Pref 1"})
        LearningStore.save_from_learning_data(db_conn, ld)

        result = load_learning_from_db(db_conn)
        assert result.project_name == "Test"
        assert len(result.preferences) == 1


class TestPersistLearning:
    def test_persists_to_db(self, temp_project_dir):
        ld = LearningData(project_name="Novel", review_count=2)
        ld.preferences.append({"description": "Test pref"})

        persist_learning(ld, temp_project_dir)

        conn = get_connection(temp_project_dir)
        try:
            data = LearningStore.load(conn)
            assert data["project_name"] == "Novel"
            assert len(data["preferences"]) == 1
        finally:
            conn.close()


class TestGenerateLearningMarkdown:
    def test_includes_header(self):
        result = generate_learning_markdown(LearningData())
        assert "# Learning" in result

    def test_includes_project_name(self):
        result = generate_learning_markdown(LearningData(project_name="Test"))
        assert "PROJECT: Test" in result

    def test_includes_review_count(self):
        result = generate_learning_markdown(LearningData(review_count=5))
        assert "REVIEW_COUNT: 5" in result

    def test_includes_sections(self):
        result = generate_learning_markdown(LearningData())
        assert "## Preferences" in result
        assert "## Blind Spots" in result
        assert "## Resolutions" in result
        assert "## Ambiguity Patterns" in result

    def test_empty_sections_show_placeholder(self):
        result = generate_learning_markdown(LearningData())
        assert "[none yet]" in result

    def test_includes_preferences(self):
        ld = LearningData()
        ld.preferences.append({"description": "Test preference"})
        result = generate_learning_markdown(ld)
        assert "- Test preference" in result


class TestExportLearningMarkdown:
    def test_creates_file(self, temp_project_dir):
        # Seed some data
        ld = LearningData(project_name="Test", review_count=1)
        persist_learning(ld, temp_project_dir)

        filepath = export_learning_markdown(temp_project_dir)
        assert filepath.exists()
        assert filepath.name == "LEARNING.md"
        content = filepath.read_text(encoding='utf-8')
        assert "PROJECT: Test" in content


class TestSaveLearningToFile:
    def test_saves_to_db_and_file(self, temp_project_dir):
        ld = LearningData(project_name="Novel", review_count=0)
        filepath = save_learning_to_file(ld, temp_project_dir)

        # File exists
        assert filepath.exists()
        assert "Novel" in filepath.read_text(encoding='utf-8')

        # review_count is NOT incremented by save_learning_to_file() — it is
        # incremented once at session completion via
        # LearningStore.increment_review_count().
        conn = get_connection(temp_project_dir)
        try:
            data = LearningStore.load(conn)
            assert data["review_count"] == 0
        finally:
            conn.close()


class TestUpdateLearningFromSession:
    def test_does_not_increment_review_count(self):
        """review_count is incremented at session completion, not here."""
        ld = LearningData(review_count=5)
        update_learning_from_session(ld)
        assert ld.review_count == 5  # unchanged

    def test_rejections_to_preferences(self):
        ld = LearningData()
        ld.session_rejections.append({
            "lens": "prose", "pattern": "fragment", "reason": "intentional"
        })
        update_learning_from_session(ld)
        assert len(ld.preferences) == 1
        assert "[prose]" in ld.preferences[0]["description"]

    def test_no_duplicate_preferences(self):
        ld = LearningData()
        ld.preferences.append({
            "description": "[prose] fragment — Author says: \"intentional\""
        })
        ld.session_rejections.append({
            "lens": "prose", "pattern": "fragment", "reason": "intentional"
        })
        update_learning_from_session(ld)
        assert len(ld.preferences) == 1

    def test_preference_rule_used(self):
        ld = LearningData()
        ld.session_rejections.append({
            "lens": "prose", "pattern": "fragment", "reason": "voice",
            "preference_rule": "Fragments are intentional for voice"
        })
        update_learning_from_session(ld)
        assert "Fragments are intentional" in ld.preferences[0]["description"]
        assert "Author says:" not in ld.preferences[0]["description"]

    def test_intentional_ambiguity(self):
        ld = LearningData()
        ld.session_ambiguity_answers.append({
            "location": "Ch3", "description": "Dream", "intentional": True
        })
        update_learning_from_session(ld)
        assert len(ld.ambiguity_intentional) == 1

    def test_accidental_ambiguity(self):
        ld = LearningData()
        ld.session_ambiguity_answers.append({
            "location": "P42", "description": "Unclear", "intentional": False
        })
        update_learning_from_session(ld)
        assert len(ld.ambiguity_accidental) == 1


class TestRoundtrip:
    def test_full_roundtrip(self, temp_project_dir):
        original = LearningData(project_name="Roundtrip", review_count=10)
        original.preferences.append({"description": "Pref 1"})
        original.blind_spots.append({"description": "Blind 1"})
        original.ambiguity_intentional.append({"description": "Intent 1"})

        initial_count = original.review_count
        save_learning_to_file(original, temp_project_dir)

        loaded = load_learning(temp_project_dir)
        assert loaded.project_name == original.project_name
        # review_count is unchanged — it is incremented once at session
        # completion via LearningStore.increment_review_count(), not here.
        assert loaded.review_count == initial_count
        assert len(loaded.preferences) == 1
        assert len(loaded.blind_spots) == 1
        assert len(loaded.ambiguity_intentional) == 1
