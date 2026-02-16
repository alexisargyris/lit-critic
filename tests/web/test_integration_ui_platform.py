"""UI -> Platform integration tests with mocked Core-facing analysis calls."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from lit_platform.runtime.models import LensResult
from web.app import app
from web.routes import session_mgr


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def reset_session_mgr():
    session_mgr.state = None
    session_mgr.results = None
    session_mgr.current_index = 0
    session_mgr.analysis_progress = None
    yield
    session_mgr.state = None
    session_mgr.results = None
    session_mgr.current_index = 0
    session_mgr.analysis_progress = None


def test_analyze_route_flows_ui_to_platform_with_mocked_core(client, temp_project_dir, reset_session_mgr):
    """POST /api/analyze drives Web -> Platform flow while Core-facing calls are mocked."""
    fake_lens_result = LensResult(lens_name="prose", findings=[], raw_output="[]")
    fake_coordinated = {
        "findings": [
            {
                "number": 1,
                "severity": "major",
                "lens": "prose",
                "location": "Paragraph 1",
                "evidence": "Repeated sentence starts",
                "impact": "Monotony",
                "options": ["Vary openings"],
                "flagged_by": ["prose"],
            }
        ],
        "glossary_issues": [],
    }

    with patch("web.session_manager.create_client", return_value=object()), patch(
        "web.session_manager.run_lens", new=AsyncMock(return_value=fake_lens_result)
    ), patch(
        "web.session_manager.run_coordinator_chunked", new=AsyncMock(return_value=fake_coordinated)
    ):
        response = client.post(
            "/api/analyze",
            json={
                "scene_path": str(temp_project_dir / "chapter01.md"),
                "project_path": str(temp_project_dir),
                "api_key": "sk-ant-test",
                "model": "sonnet",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_findings"] == 1
    assert data["current_index"] == 0

    finding_response = client.get("/api/finding")
    assert finding_response.status_code == 200
    finding_data = finding_response.json()
    assert finding_data["complete"] is False
    assert finding_data["finding"]["number"] == 1
    assert finding_data["finding"]["lens"] == "prose"
