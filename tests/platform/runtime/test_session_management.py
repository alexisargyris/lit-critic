"""
Tests for session management functions (Phase 2).

Tests list_sessions(), get_session_detail(), delete_session_by_id()
"""

import pytest
from datetime import datetime
from pathlib import Path
from lit_platform.runtime.session import (
    list_sessions, get_session_detail, delete_session_by_id,
    create_session, complete_session, abandon_session, load_active_session
)
from lit_platform.runtime.models import Finding, LearningData


class TestListSessions:
    """Tests for list_sessions function."""

    def test_returns_empty_list_for_new_project(self, temp_project_dir):
        """A brand new project should have no sessions."""
        sessions = list_sessions(temp_project_dir)
        assert sessions == []

    def test_returns_all_sessions(self, temp_project_dir, sample_session_state_with_db):
        """Should return all sessions for a project."""
        # Create a few sessions
        state1 = sample_session_state_with_db
        state1.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"])
        ]
        create_session(state1)
        complete_session(state1)

        # Create another session
        state2 = sample_session_state_with_db
        state2.scene_path = str(temp_project_dir / "scene02.txt")
        state2.findings = [
            Finding(number=1, severity="critical", lens="structure", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["structure"]),
            Finding(number=2, severity="minor", lens="clarity", location="P2",
                   evidence="E2", impact="I2", options=["O2"], flagged_by=["clarity"]),
        ]
        create_session(state2)

        sessions = list_sessions(temp_project_dir)
        
        assert len(sessions) == 2
        assert all('id' in s for s in sessions)
        assert all('status' in s for s in sessions)
        assert all('scene_path' in s for s in sessions)

    def test_includes_summary_data(self, temp_project_dir, sample_session_state_with_db):
        """Sessions should include finding counts and metadata."""
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="critical", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"],
                   status="accepted"),
            Finding(number=2, severity="major", lens="structure", location="P2",
                   evidence="E2", impact="I2", options=["O2"], flagged_by=["structure"],
                   status="rejected"),
            Finding(number=3, severity="minor", lens="clarity", location="P3",
                   evidence="E3", impact="I3", options=["O3"], flagged_by=["clarity"],
                   status="withdrawn"),
        ]
        create_session(state)
        assert complete_session(state) is True

        sessions = list_sessions(temp_project_dir)
        
        assert len(sessions) == 1
        session = sessions[0]
        
        assert session['total_findings'] == 3
        assert session['accepted_count'] == 1
        assert session['rejected_count'] == 1
        assert session['withdrawn_count'] == 1
        assert 'model' in session
        assert 'created_at' in session

    def test_groups_by_status(self, temp_project_dir, sample_session_state_with_db):
        """Should return sessions with different statuses."""
        # Create sessions with different statuses
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"],
                   status="accepted")
        ]
        
        # Completed session
        create_session(state)
        assert complete_session(state) is True
        
        # Active session
        state.scene_path = str(temp_project_dir / "scene02.txt")
        create_session(state)
        
        # Abandoned session
        state.scene_path = str(temp_project_dir / "scene03.txt")
        create_session(state)
        abandon_session(state)

        sessions = list_sessions(temp_project_dir)
        
        assert len(sessions) == 3
        statuses = {s['status'] for s in sessions}
        assert statuses == {'active', 'completed', 'abandoned'}


class TestGetSessionDetail:
    """Tests for get_session_detail function."""

    def test_returns_none_for_nonexistent_session(self, temp_project_dir):
        """Should return None when session doesn't exist."""
        detail = get_session_detail(temp_project_dir, 9999)
        assert detail is None

    def test_returns_full_session_details(self, temp_project_dir, sample_session_state_with_db):
        """Should return complete session data including findings."""
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="critical", lens="prose", location="Paragraph 1",
                   evidence="Test evidence", impact="Test impact", options=["Fix it"],
                   flagged_by=["prose"], status="accepted"),
            Finding(number=2, severity="major", lens="structure", location="Scene opening",
                   evidence="Missing goal", impact="Reader confusion", options=["Add goal"],
                   flagged_by=["structure"], status="rejected"),
        ]
        create_session(state)
        complete_session(state)

        # Get the session ID (should be 1 for first session)
        sessions = list_sessions(temp_project_dir)
        session_id = sessions[0]['id']

        detail = get_session_detail(temp_project_dir, session_id)
        
        assert detail is not None
        assert detail['id'] == session_id
        assert detail['status'] == 'completed'
        assert 'scene_path' in detail
        assert 'model' in detail
        assert 'created_at' in detail
        assert 'findings' in detail
        assert len(detail['findings']) == 2

    def test_includes_all_metadata(self, temp_project_dir, sample_session_state_with_db):
        """Should include all session metadata."""
        state = sample_session_state_with_db
        state.findings = []
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        session_id = sessions[0]['id']
        
        detail = get_session_detail(temp_project_dir, session_id)
        
        assert 'total_findings' in detail
        assert 'accepted_count' in detail
        assert 'rejected_count' in detail
        assert 'withdrawn_count' in detail
        assert 'completed_at' in detail
        assert detail['completed_at'] is not None  # Status is 'completed'

    def test_finding_data_is_complete(self, temp_project_dir, sample_session_state_with_db):
        """Findings should include all required fields."""
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="Evidence text", impact="Impact text", 
                   options=["Option 1", "Option 2"],
                   flagged_by=["prose"], status="accepted",
                   line_start=5, line_end=10)
        ]
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        detail = get_session_detail(temp_project_dir, sessions[0]['id'])
        
        finding = detail['findings'][0]
        assert finding['number'] == 1
        assert finding['severity'] == 'major'
        assert finding['lens'] == 'prose'
        assert finding['location'] == 'P1'
        assert finding['evidence'] == 'Evidence text'
        assert finding['impact'] == 'Impact text'
        assert finding['options'] == ["Option 1", "Option 2"]
        assert finding['status'] == 'accepted'
        assert finding['line_start'] == 5
        assert finding['line_end'] == 10


class TestDeleteSession:
    """Tests for delete_session_by_id function."""

    def test_returns_false_for_nonexistent_session(self, temp_project_dir):
        """Should return False when session doesn't exist."""
        result = delete_session_by_id(temp_project_dir, 9999)
        assert result is False

    def test_deletes_session_and_returns_true(self, temp_project_dir, sample_session_state_with_db):
        """Should delete session and return True."""
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"])
        ]
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        assert len(sessions) == 1
        session_id = sessions[0]['id']

        result = delete_session_by_id(temp_project_dir, session_id)
        assert result is True

        # Verify it's gone
        sessions_after = list_sessions(temp_project_dir)
        assert len(sessions_after) == 0

    def test_cascades_to_delete_findings(self, temp_project_dir, sample_session_state_with_db):
        """Deleting a session should also delete its findings."""
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="prose", location="P1",
                   evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"]),
            Finding(number=2, severity="critical", lens="structure", location="P2",
                   evidence="E2", impact="I2", options=["O2"], flagged_by=["structure"]),
        ]
        create_session(state)
        complete_session(state)

        sessions = list_sessions(temp_project_dir)
        session_id = sessions[0]['id']

        # Verify findings exist
        detail_before = get_session_detail(temp_project_dir, session_id)
        assert len(detail_before['findings']) == 2

        # Delete session
        delete_session_by_id(temp_project_dir, session_id)

        # Verify detail no longer accessible
        detail_after = get_session_detail(temp_project_dir, session_id)
        assert detail_after is None

    def test_deletes_specific_session_not_others(self, temp_project_dir, sample_session_state_with_db):
        """Should only delete the specified session."""
        # Create two sessions
        state1 = sample_session_state_with_db
        state1.findings = [Finding(number=1, severity="major", lens="prose", location="P1",
                                  evidence="E1", impact="I1", options=["O1"], flagged_by=["prose"])]
        create_session(state1)
        complete_session(state1)

        state2 = sample_session_state_with_db
        state2.scene_path = str(temp_project_dir / "scene02.txt")
        state2.findings = [Finding(number=1, severity="critical", lens="structure", location="P1",
                                  evidence="E1", impact="I1", options=["O1"], flagged_by=["structure"])]
        create_session(state2)

        sessions = list_sessions(temp_project_dir)
        assert len(sessions) == 2
        first_id = sessions[0]['id']

        # Delete first session
        delete_session_by_id(temp_project_dir, first_id)

        # Verify only one remains
        sessions_after = list_sessions(temp_project_dir)
        assert len(sessions_after) == 1
        assert sessions_after[0]['id'] != first_id
