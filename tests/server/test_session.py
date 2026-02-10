"""
Tests for lit-critic.session module.
"""

import json
import pytest
from pathlib import Path
from server.session import (
    compute_scene_hash,
    get_session_file_path,
    session_exists,
    save_session,
    load_session,
    delete_session,
    validate_session,
)
from server.config import SESSION_FILE
from server.models import Finding


class TestComputeSceneHash:
    """Tests for compute_scene_hash function."""
    
    def test_returns_string(self):
        """Hash should be a string."""
        result = compute_scene_hash("test content")
        assert isinstance(result, str)
    
    def test_consistent_hash(self):
        """Same content should produce same hash."""
        content = "The quick brown fox"
        hash1 = compute_scene_hash(content)
        hash2 = compute_scene_hash(content)
        assert hash1 == hash2
    
    def test_different_content_different_hash(self):
        """Different content should produce different hash."""
        hash1 = compute_scene_hash("content one")
        hash2 = compute_scene_hash("content two")
        assert hash1 != hash2
    
    def test_hash_length(self):
        """Hash should be truncated to expected length."""
        result = compute_scene_hash("test")
        assert len(result) == 16  # Truncated to 16 chars


class TestGetSessionFilePath:
    """Tests for get_session_file_path function."""
    
    def test_returns_path(self, tmp_path):
        """Should return a Path object."""
        result = get_session_file_path(tmp_path)
        assert isinstance(result, Path)
    
    def test_path_includes_session_file(self, tmp_path):
        """Path should include the session filename."""
        result = get_session_file_path(tmp_path)
        assert result.name == SESSION_FILE
        assert result.parent == tmp_path


class TestSessionExists:
    """Tests for session_exists function."""
    
    def test_returns_false_when_no_session(self, tmp_path):
        """Should return False when no session file exists."""
        assert session_exists(tmp_path) is False
    
    def test_returns_true_when_session_exists(self, tmp_path):
        """Should return True when session file exists."""
        session_path = tmp_path / SESSION_FILE
        session_path.write_text("{}", encoding='utf-8')
        assert session_exists(tmp_path) is True


class TestSaveAndLoadSession:
    """Tests for save_session and load_session functions."""
    
    def test_save_creates_file(self, sample_session_state):
        """save_session should create a session file."""
        filepath = save_session(sample_session_state, current_index=0)
        assert filepath.exists()
    
    def test_save_returns_path(self, sample_session_state):
        """save_session should return the file path."""
        filepath = save_session(sample_session_state, current_index=0)
        assert isinstance(filepath, Path)
        assert filepath.name == SESSION_FILE
    
    def test_saved_file_is_valid_json(self, sample_session_state):
        """Saved session should be valid JSON."""
        filepath = save_session(sample_session_state, current_index=0)
        content = filepath.read_text(encoding='utf-8')
        data = json.loads(content)  # Should not raise
        assert isinstance(data, dict)
    
    def test_load_returns_dict(self, sample_session_state):
        """load_session should return a dictionary."""
        save_session(sample_session_state, current_index=0)
        result = load_session(sample_session_state.project_path)
        assert isinstance(result, dict)
    
    def test_load_returns_none_when_no_file(self, tmp_path):
        """load_session should return None when no file exists."""
        result = load_session(tmp_path)
        assert result is None
    
    def test_roundtrip_preserves_data(self, sample_session_state):
        """Save and load should preserve session data."""
        # Add some findings
        finding = Finding(
            number=1,
            severity="major",
            lens="prose",
            location="Test location",
            evidence="Test evidence",
            impact="Test impact",
            options=["Option 1"],
        )
        finding.status = "accepted"
        sample_session_state.findings = [finding]
        sample_session_state.glossary_issues = ["Test glossary issue"]
        
        save_session(sample_session_state, current_index=5, skip_minor=True)
        loaded = load_session(sample_session_state.project_path)
        
        assert loaded["current_index"] == 5
        assert loaded["skip_minor"] is True
        assert len(loaded["findings"]) == 1
        assert loaded["findings"][0]["status"] == "accepted"
        assert loaded["glossary_issues"] == ["Test glossary issue"]
    
    def test_saves_scene_hash(self, sample_session_state):
        """Session should include scene hash for validation."""
        save_session(sample_session_state, current_index=0)
        loaded = load_session(sample_session_state.project_path)
        
        assert "scene_hash" in loaded
        expected_hash = compute_scene_hash(sample_session_state.scene_content)
        assert loaded["scene_hash"] == expected_hash
    
    def test_saves_learning_session_data(self, sample_session_state):
        """Session should include learning session data."""
        sample_session_state.learning.session_rejections.append({
            "lens": "prose",
            "pattern": "test pattern",
            "reason": "not an issue"
        })
        
        save_session(sample_session_state, current_index=0)
        loaded = load_session(sample_session_state.project_path)
        
        assert "learning_session" in loaded
        assert len(loaded["learning_session"]["session_rejections"]) == 1


class TestDeleteSession:
    """Tests for delete_session function."""
    
    def test_delete_returns_true_when_exists(self, sample_session_state):
        """delete_session should return True when file existed."""
        save_session(sample_session_state, current_index=0)
        result = delete_session(sample_session_state.project_path)
        assert result is True
    
    def test_delete_returns_false_when_not_exists(self, tmp_path):
        """delete_session should return False when no file exists."""
        result = delete_session(tmp_path)
        assert result is False
    
    def test_delete_removes_file(self, sample_session_state):
        """delete_session should actually remove the file."""
        filepath = save_session(sample_session_state, current_index=0)
        assert filepath.exists()
        
        delete_session(sample_session_state.project_path)
        assert not filepath.exists()


class TestValidateSession:
    """Tests for validate_session function."""
    
    def test_valid_session(self, sample_session_state):
        """Should return (True, '') for valid session."""
        save_session(sample_session_state, current_index=0)
        session_data = load_session(sample_session_state.project_path)
        
        is_valid, error = validate_session(
            session_data,
            sample_session_state.scene_content,
            sample_session_state.scene_path
        )
        
        assert is_valid is True
        assert error == ""
    
    def test_none_session_data(self):
        """Should return invalid for None session data."""
        is_valid, error = validate_session(None, "content", "/path/scene.md")
        assert is_valid is False
        assert "No session data" in error
    
    def test_different_scene_path(self, sample_session_state):
        """Should return invalid if scene path changed."""
        save_session(sample_session_state, current_index=0)
        session_data = load_session(sample_session_state.project_path)
        
        is_valid, error = validate_session(
            session_data,
            sample_session_state.scene_content,
            "/different/path/scene.md"
        )
        
        assert is_valid is False
        assert "different scene" in error.lower()
    
    def test_modified_scene_content(self, sample_session_state):
        """Should return invalid if scene content changed."""
        save_session(sample_session_state, current_index=0)
        session_data = load_session(sample_session_state.project_path)
        
        is_valid, error = validate_session(
            session_data,
            "Modified scene content that is different",
            sample_session_state.scene_path
        )
        
        assert is_valid is False
        assert "modified" in error.lower()


class TestDetectAndApplySceneChanges:
    """Tests for detect_and_apply_scene_changes function."""

    async def test_returns_none_when_unchanged(self, sample_session_state):
        """Should return None when scene file hasn't changed."""
        from server.session import detect_and_apply_scene_changes
        result = await detect_and_apply_scene_changes(sample_session_state, 0)
        assert result is None

    async def test_detects_file_change(self, sample_session_state):
        """Should detect when scene file has been modified."""
        from server.session import detect_and_apply_scene_changes
        from unittest.mock import AsyncMock, patch

        # Add a finding with line numbers
        finding = Finding(
            number=1, severity="major", lens="prose",
            location="P1", line_start=8, line_end=8,
            evidence="Test", impact="Test", options=["Fix"],
        )
        sample_session_state.findings = [finding]

        # Modify the scene file on disk
        scene_path = Path(sample_session_state.scene_path)
        new_content = "New first line\n" + sample_session_state.scene_content
        scene_path.write_text(new_content, encoding='utf-8')

        # Mock re_evaluate_finding to avoid actual API calls (lazy import in session.py)
        with patch('server.api.re_evaluate_finding', new_callable=AsyncMock) as mock_re_eval:
            result = await detect_and_apply_scene_changes(sample_session_state, 0)

        assert result is not None
        assert result["changed"] is True
        # scene_content should be updated
        assert sample_session_state.scene_content == new_content

    async def test_adjusts_line_numbers(self, sample_session_state):
        """Should adjust finding line numbers when lines are inserted."""
        from server.session import detect_and_apply_scene_changes
        from unittest.mock import AsyncMock, patch

        finding = Finding(
            number=1, severity="major", lens="prose",
            location="P1", line_start=8, line_end=10,
            evidence="Test", impact="Test", options=["Fix"],
        )
        sample_session_state.findings = [finding]

        # Insert a line at the beginning
        scene_path = Path(sample_session_state.scene_path)
        new_content = "INSERTED LINE\n" + sample_session_state.scene_content
        scene_path.write_text(new_content, encoding='utf-8')

        with patch('server.api.re_evaluate_finding', new_callable=AsyncMock):
            result = await detect_and_apply_scene_changes(sample_session_state, 0)

        assert result["adjusted"] == 1
        assert finding.line_start == 9  # shifted by 1

    async def test_marks_stale_and_re_evaluates(self, sample_session_state):
        """Should mark findings as stale and call re_evaluate_finding."""
        from server.session import detect_and_apply_scene_changes
        from unittest.mock import AsyncMock, patch

        # Finding on line 8 (will be deleted)
        finding = Finding(
            number=1, severity="major", lens="prose",
            location="P1", line_start=8, line_end=8,
            evidence="Test", impact="Test", options=["Fix"],
        )
        sample_session_state.findings = [finding]

        # Remove line 8 from scene
        lines = sample_session_state.scene_content.splitlines()
        new_lines = lines[:7] + lines[8:]  # skip line 8 (0-indexed: 7)
        new_content = "\n".join(new_lines)
        scene_path = Path(sample_session_state.scene_path)
        scene_path.write_text(new_content, encoding='utf-8')

        mock_re_eval = AsyncMock(return_value={"status": "updated", "finding_number": 1})
        with patch('server.api.re_evaluate_finding', mock_re_eval):
            result = await detect_and_apply_scene_changes(sample_session_state, 0)

        assert result["stale"] == 1
        assert mock_re_eval.called

    async def test_returns_none_when_file_missing(self, sample_session_state):
        """Should return None when scene file doesn't exist."""
        from server.session import detect_and_apply_scene_changes
        import os
        os.remove(sample_session_state.scene_path)
        result = await detect_and_apply_scene_changes(sample_session_state, 0)
        assert result is None

    async def test_skips_withdrawn_for_re_evaluation(self, sample_session_state):
        """Withdrawn findings should not be re-evaluated."""
        from server.session import detect_and_apply_scene_changes
        from unittest.mock import AsyncMock, patch

        finding = Finding(
            number=1, severity="major", lens="prose",
            location="P1", line_start=8, line_end=8,
            evidence="Test", impact="Test", options=["Fix"],
        )
        finding.status = "withdrawn"
        sample_session_state.findings = [finding]

        # Delete line 8
        lines = sample_session_state.scene_content.splitlines()
        new_lines = lines[:7] + lines[8:]
        new_content = "\n".join(new_lines)
        Path(sample_session_state.scene_path).write_text(new_content, encoding='utf-8')

        mock_re_eval = AsyncMock()
        with patch('server.api.re_evaluate_finding', mock_re_eval):
            result = await detect_and_apply_scene_changes(sample_session_state, 0)

        assert result["stale"] == 1
        # withdrawn findings should NOT be re-evaluated
        mock_re_eval.assert_not_called()
