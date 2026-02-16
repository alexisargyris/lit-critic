"""Integration tests for the stateless core FastAPI endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

import core.api as core_api
from contracts.v1.schemas import (
    AnalyzeResponse,
    DiscussAction,
    DiscussResponse,
    FindingContract,
    MetaContract,
    ReEvaluateFindingResponse,
)


def test_health_returns_ok():
    client = TestClient(core_api.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_v1_uses_resolved_model_id_and_returns_contract(monkeypatch):
    captured = {}

    async def _fake_analyze(request, *, client):
        captured["model"] = request.model_settings.analysis_model
        return AnalyzeResponse(
            findings=[],
            glossary_issues=[],
            meta=MetaContract(model_used=request.model_settings.analysis_model),
        )

    monkeypatch.setattr(core_api, "create_client", lambda provider, api_key: object())
    monkeypatch.setattr(core_api.core_service, "analyze", _fake_analyze)

    client = TestClient(core_api.app)
    response = client.post(
        "/v1/analyze",
        json={
            "scene_text": "Scene text",
            "indexes": {},
            "model_config": {
                "analysis_model": "sonnet",
                "api_keys": {"anthropic": "sk-ant-test"},
                "max_tokens": 512,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["findings"] == []
    assert captured["model"] == "claude-sonnet-4-5-20250929"


def test_discuss_v1_returns_contract(monkeypatch):
    async def _fake_discuss(request, *, discussion_client):
        return DiscussResponse(
            assistant_response="Thanks for the clarification.",
            action=DiscussAction(type="defend", payload={"legacy_status": "continue"}),
            updated_finding=FindingContract(**request.finding.model_dump()),
            extracted_preference=None,
            meta=MetaContract(model_used=request.model_settings.discussion_model),
        )

    monkeypatch.setattr(core_api, "create_client", lambda provider, api_key: object())
    monkeypatch.setattr(core_api.core_service, "discuss", _fake_discuss)

    client = TestClient(core_api.app)
    response = client.post(
        "/v1/discuss",
        json={
            "scene_text": "Scene text",
            "finding": {
                "number": 1,
                "severity": "major",
                "lens": "prose",
                "location": "Paragraph 1",
                "evidence": "Repeated sentence openings",
                "impact": "Monotony",
                "options": ["Vary openings"],
                "flagged_by": ["prose"],
                "stale": False,
            },
            "discussion_context": {"discussion_turns": []},
            "author_message": "This cadence is intentional.",
            "model_config": {
                "discussion_model": "gpt-4o",
                "api_keys": {"openai": "sk-openai-test"},
                "max_tokens": 512,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["assistant_response"] == "Thanks for the clarification."
    assert response.json()["action"]["type"] == "defend"


def test_re_evaluate_v1_returns_contract(monkeypatch):
    async def _fake_re_evaluate(request, *, client):
        return ReEvaluateFindingResponse(
            status="withdrawn",
            updated_finding=None,
            reason="Issue resolved by scene edit.",
            meta=MetaContract(model_used=request.model_settings.analysis_model),
        )

    monkeypatch.setattr(core_api, "create_client", lambda provider, api_key: object())
    monkeypatch.setattr(core_api.core_service, "re_evaluate", _fake_re_evaluate)

    client = TestClient(core_api.app)
    response = client.post(
        "/v1/re-evaluate-finding",
        json={
            "stale_finding": {
                "number": 2,
                "severity": "minor",
                "lens": "clarity",
                "location": "Paragraph 2",
                "evidence": "Unclear referent",
                "impact": "Reader uncertainty",
                "options": ["Name the character"],
                "flagged_by": ["clarity"],
                "stale": True,
            },
            "updated_scene_text": "Updated scene text",
            "model_config": {
                "analysis_model": "sonnet",
                "api_keys": {"anthropic": "sk-ant-test"},
                "max_tokens": 512,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"


def test_analyze_v1_returns_400_when_provider_key_missing(monkeypatch):
    monkeypatch.setattr(core_api, "create_client", lambda provider, api_key: object())
    client = TestClient(core_api.app)

    with patch.dict("os.environ", {}, clear=True):
        response = client.post(
            "/v1/analyze",
            json={
                "scene_text": "Scene text",
                "indexes": {},
                "model_config": {
                    "analysis_model": "sonnet",
                    "api_keys": {},
                    "max_tokens": 512,
                },
            },
        )

    assert response.status_code == 400
    assert "No API key for provider 'anthropic'" in response.json()["detail"]
