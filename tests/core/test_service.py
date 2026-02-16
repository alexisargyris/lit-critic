"""Unit tests for core.service decoupled port orchestration."""

from __future__ import annotations

from contracts.v1.schemas import (
    AnalyzeModelConfig,
    AnalyzeRequest,
    DiscussModelConfig,
    DiscussRequest,
    FindingContract,
    IndexesContract,
    ReEvaluateFindingRequest,
)
from core.domain import CoreFinding
from core.service import analyze, discuss, re_evaluate


class _FakeAnalysisPort:
    async def analyze(self, **kwargs):
        return {
            "findings": [
                {
                    "number": 1,
                    "severity": "major",
                    "lens": "prose",
                    "location": "Paragraph 1",
                    "line_start": 1,
                    "line_end": 2,
                    "evidence": "Repeated starts",
                    "impact": "Monotony",
                    "options": ["Vary openings"],
                    "flagged_by": ["prose"],
                }
            ],
            "glossary_issues": [],
        }


class _FakeDiscussionPort:
    async def discuss(self, **kwargs):
        finding: CoreFinding = kwargs["finding"]
        finding.status = "accepted"
        finding.discussion_turns.append({"role": "assistant", "content": "Accepted."})
        return "Accepted.", "accepted", finding


class _FakeReEvalPort:
    async def re_evaluate(self, **kwargs):
        return {"status": "withdrawn", "reason": "No longer applies."}


async def test_analyze_uses_injected_analysis_port():
    req = AnalyzeRequest(
        scene_text="Scene",
        indexes=IndexesContract(),
        model_settings=AnalyzeModelConfig(
            analysis_model="claude-sonnet-4-5-20250929",
            api_keys={},
            max_tokens=512,
        ),
    )

    res = await analyze(req, client=object(), analysis_engine=_FakeAnalysisPort())

    assert len(res.findings) == 1
    assert res.findings[0].severity == "major"


async def test_discuss_uses_injected_discussion_port():
    req = DiscussRequest(
        scene_text="Scene",
        finding=FindingContract(
            number=1,
            severity="major",
            lens="prose",
            location="Paragraph 1",
            evidence="Repeated starts",
            impact="Monotony",
            options=["Vary openings"],
            flagged_by=["prose"],
        ),
        discussion_context={"discussion_turns": []},
        author_message="I changed it.",
        model_settings=DiscussModelConfig(
            discussion_model="gpt-4o",
            api_keys={},
            max_tokens=256,
        ),
    )

    res = await discuss(
        req,
        discussion_client=object(),
        discussion_engine=_FakeDiscussionPort(),
    )

    assert res.assistant_response == "Accepted."
    assert res.action.payload["legacy_status"] == "accepted"


async def test_re_evaluate_uses_injected_re_eval_port():
    req = ReEvaluateFindingRequest(
        stale_finding=FindingContract(
            number=2,
            severity="minor",
            lens="clarity",
            location="Paragraph 2",
            evidence="Unclear referent",
            impact="Reader uncertainty",
            options=["Name character"],
            flagged_by=["clarity"],
            stale=True,
        ),
        updated_scene_text="Updated",
        model_settings=AnalyzeModelConfig(
            analysis_model="claude-sonnet-4-5-20250929",
            api_keys={},
            max_tokens=256,
        ),
    )

    res = await re_evaluate(req, client=object(), re_evaluation_engine=_FakeReEvalPort())

    assert res.status == "withdrawn"
    assert res.reason == "No longer applies."
