"""UI -> Platform integration tests with mocked Core-facing analysis calls."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from lit_platform.runtime.models import LensResult
from web.app import app
from web.routes import session_mgr
from web.session_manager import resolve_model


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

    with patch("web.routes_analysis.ensure_project_knowledge_fresh"), patch(
        "web.session_manager.ensure_project_knowledge_fresh"
    ), patch(
        "web.session_manager.create_client", return_value=object()
    ), patch(
        "web.session_manager.run_code_checks", return_value=[]
    ), patch(
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
                "mode": "deep",
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


def test_analyze_route_dispatches_mixed_models_and_persists_tier_metadata(
    client, temp_project_dir, reset_session_mgr
):
    """POST /api/analyze routes critic lenses to frontier and checker paths to checker tier."""
    checker_client = object()

    lens_calls = []

    async def _fake_run_lens(client_obj, lens_name, scene, indexes, **kwargs):
        lens_calls.append(
            {
                "lens": lens_name,
                "model": kwargs.get("model"),
                "max_tokens": kwargs.get("max_tokens"),
            }
        )
        return LensResult(lens_name=lens_name, findings=[], raw_output="[]")

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
                "origin": "llm",
            }
        ],
        "glossary_issues": [],
    }

    expected_frontier = resolve_model("sonnet")
    expected_checker = resolve_model("haiku")

    run_coordinator_mock = AsyncMock(return_value=fake_coordinated)

    with patch("web.routes_analysis.ensure_project_knowledge_fresh"), patch(
        "web.session_manager.ensure_project_knowledge_fresh"
    ), patch(
        "web.session_manager.resolve_models_for_mode",
        return_value={
            "mode": "deep",
            "frontier_model": "sonnet",
            "checker_model": "haiku",
        },
    ), patch("web.session_manager.create_client", return_value=checker_client), patch(
        "web.session_manager.run_code_checks", return_value=[]
    ), patch("web.session_manager.run_lens", new=AsyncMock(side_effect=_fake_run_lens)), patch(
        "web.session_manager.run_coordinator_chunked", new=run_coordinator_mock
    ):
        response = client.post(
            "/api/analyze",
            json={
                "scene_path": str(temp_project_dir / "chapter01.md"),
                "project_path": str(temp_project_dir),
                "api_key": "sk-ant-test",
                "mode": "deep",
                "frontier_model": "sonnet",
                "checker_model": "haiku",
            },
        )

    assert response.status_code == 200

    frontier_lenses = {"prose", "structure", "horizon"}
    checker_lenses = {"logic", "clarity", "continuity", "dialogue"}

    assert len(lens_calls) == 7
    for call in lens_calls:
        if call["lens"] in frontier_lenses:
            assert call["model"] == expected_frontier["id"]
            assert call["max_tokens"] == expected_frontier["max_tokens"]
        elif call["lens"] in checker_lenses:
            assert call["model"] == expected_checker["id"]
            assert call["max_tokens"] == expected_checker["max_tokens"]
        else:
            pytest.fail(f"Unexpected lens: {call['lens']}")

    coord_call = run_coordinator_mock.await_args
    assert coord_call is not None
    assert coord_call.args[0] is checker_client
    assert coord_call.kwargs["model"] == expected_checker["id"]
    assert coord_call.kwargs["max_tokens"] == expected_checker["max_tokens"]

    summary_response = client.get("/api/session")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["model"] == {
        "name": "haiku",
        "id": expected_checker["id"],
        "label": expected_checker["label"],
    }
    assert summary["discussion_model"] == {
        "name": "sonnet",
        "id": expected_frontier["id"],
        "label": expected_frontier["label"],
    }


def test_web_review_template_includes_origin_badge_slot(client):
    """Review UI includes a dedicated origin badge element for findings."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="finding-origin"' in response.text
    assert 'class="origin-badge hidden"' in response.text


def test_web_assets_define_and_render_origin_badges(client):
    """Static assets include origin badge styling and render logic for supported origins."""
    js_response = client.get("/static/js/app.js")
    assert js_response.status_code == 200
    assert "const originBadge = document.getElementById('finding-origin');" in js_response.text
    assert "const displayOrigin = origin === 'llm' ? 'critic' : origin;" in js_response.text
    assert "const supportedOrigins = ['code', 'checker', 'critic'];" in js_response.text

    css_response = client.get("/static/css/style.css")
    assert css_response.status_code == 200
    assert ".origin-badge.code" in css_response.text
    assert ".origin-badge.checker" in css_response.text
    assert ".origin-badge.critic" in css_response.text
