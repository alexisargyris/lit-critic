"""Stateless core orchestration service (text/context in, structured out)."""

from __future__ import annotations

import time
from typing import Any

from contracts.v1.adapters import (
    adapt_legacy_analyze_output_to_response,
    adapt_legacy_discuss_output_to_response,
    adapt_legacy_re_evaluate_output_to_response,
)
from contracts.v1.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DiscussRequest,
    DiscussResponse,
    ReEvaluateFindingRequest,
    ReEvaluateFindingResponse,
)

from .adapters.legacy_runtime import (
    LegacyAnalysisEngineAdapter,
    LegacyDiscussionEngineAdapter,
    LegacyReEvaluationEngineAdapter,
)
from .domain import CoreFinding
from .ports import AnalysisEnginePort, DiscussionEnginePort, ReEvaluationEnginePort


_ANALYSIS_ENGINE: AnalysisEnginePort = LegacyAnalysisEngineAdapter()
_DISCUSSION_ENGINE: DiscussionEnginePort = LegacyDiscussionEngineAdapter()
_RE_EVALUATION_ENGINE: ReEvaluationEnginePort = LegacyReEvaluationEngineAdapter()


def _model_used(model_name: str) -> str:
    """Report model id/label used for request metadata."""
    return model_name


def _to_server_indexes(indexes: dict[str, str | None]) -> dict[str, str]:
    mapping = {
        "CANON": "CANON.md",
        "CAST": "CAST.md",
        "GLOSSARY": "GLOSSARY.md",
        "STYLE": "STYLE.md",
        "THREADS": "THREADS.md",
        "TIMELINE": "TIMELINE.md",
    }
    return {legacy: (indexes.get(contract) or "") for contract, legacy in mapping.items()}


async def analyze(
    request: AnalyzeRequest,
    *,
    client,
    analysis_engine: AnalysisEnginePort | None = None,
) -> AnalyzeResponse:
    """Run stateless analysis against scene/index text payload."""
    started = time.perf_counter()
    engine = analysis_engine or _ANALYSIS_ENGINE
    legacy_output = await engine.analyze(
        client=client,
        scene_text=request.scene_text,
        indexes=_to_server_indexes(request.indexes.model_dump()),
        model=request.model_settings.analysis_model,
        max_tokens=request.model_settings.max_tokens,
    )
    elapsed = time.perf_counter() - started
    return adapt_legacy_analyze_output_to_response(
        legacy_output,
        model_used=_model_used(request.model_settings.analysis_model),
        timings={"total_seconds": elapsed},
    )


def _core_finding_from_discuss_request(request: DiscussRequest) -> CoreFinding:
    finding = CoreFinding.from_dict(request.finding.model_dump())
    prior_turns = request.discussion_context.get("discussion_turns", [])
    if isinstance(prior_turns, list):
        finding.discussion_turns = [
            t for t in prior_turns if isinstance(t, dict) and "role" in t and "content" in t
        ]
    return finding


async def discuss(
    request: DiscussRequest,
    *,
    discussion_client,
    discussion_engine: DiscussionEnginePort | None = None,
) -> DiscussResponse:
    """Run stateless discuss turn against provided condensed context."""
    started = time.perf_counter()
    engine = discussion_engine or _DISCUSSION_ENGINE
    response_text, status, updated_finding = await engine.discuss(
        discussion_client=discussion_client,
        scene_text=request.scene_text,
        finding=_core_finding_from_discuss_request(request),
        author_message=request.author_message,
        model=request.model_settings.discussion_model,
        max_tokens=request.model_settings.max_tokens,
    )
    elapsed = time.perf_counter() - started

    legacy_output: dict[str, Any] = {
        "response": response_text,
        "status": status,
        "finding": updated_finding.to_dict(include_state=True),
    }
    return adapt_legacy_discuss_output_to_response(
        legacy_output,
        model_used=_model_used(request.model_settings.discussion_model),
        timings={"total_seconds": elapsed},
    )


async def re_evaluate(
    request: ReEvaluateFindingRequest,
    *,
    client,
    re_evaluation_engine: ReEvaluationEnginePort | None = None,
) -> ReEvaluateFindingResponse:
    """Re-evaluate a stale finding against updated scene text (stateless)."""
    started = time.perf_counter()
    finding = CoreFinding.from_dict(request.stale_finding.model_dump())
    engine = re_evaluation_engine or _RE_EVALUATION_ENGINE
    legacy_output = await engine.re_evaluate(
        client=client,
        finding=finding,
        updated_scene_text=request.updated_scene_text,
        model=request.model_settings.analysis_model,
        max_tokens=request.model_settings.max_tokens,
    )
    elapsed = time.perf_counter() - started
    return adapt_legacy_re_evaluate_output_to_response(
        legacy_output,
        model_used=_model_used(request.model_settings.analysis_model),
        original_finding=finding.to_dict(include_state=False),
        timings={"total_seconds": elapsed},
    )
