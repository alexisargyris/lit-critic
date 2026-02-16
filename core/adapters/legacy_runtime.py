"""Temporary adapter that bridges Core ports to legacy ``server.*`` runtime."""

from __future__ import annotations

from pathlib import Path

from core.domain import CoreFinding
from core.ports import AnalysisEnginePort, DiscussionEnginePort, ReEvaluationEnginePort
from lit_platform.runtime.api import re_evaluate_finding, run_analysis
from lit_platform.runtime.discussion import handle_discussion
from lit_platform.runtime.models import Finding, SessionState


class LegacyAnalysisEngineAdapter(AnalysisEnginePort):
    """Bridge analysis port to legacy ``server.api.run_analysis``."""

    async def analyze(
        self,
        *,
        client,
        scene_text: str,
        indexes: dict[str, str],
        model: str,
        max_tokens: int,
    ) -> dict:
        return await run_analysis(
            client,
            scene_text,
            indexes,
            model=model,
            max_tokens=max_tokens,
        )


class LegacyDiscussionEngineAdapter(DiscussionEnginePort):
    """Bridge discussion port to legacy ``server.discussion.handle_discussion``."""

    async def discuss(
        self,
        *,
        discussion_client,
        scene_text: str,
        finding: CoreFinding,
        author_message: str,
        model: str,
        max_tokens: int,
    ) -> tuple[str, str, CoreFinding]:
        legacy_finding = Finding.from_dict(finding.to_dict(include_state=True))
        state = SessionState(
            client=discussion_client,
            scene_content=scene_text,
            scene_path="[stateless]",
            # Required by legacy SessionState API; never used for FS I/O in core.
            project_path=Path("[stateless]"),
            indexes={},
            findings=[legacy_finding],
            model=model,
            discussion_model=model,
            discussion_client=discussion_client,
        )

        response_text, status = await handle_discussion(
            state,
            legacy_finding,
            author_message,
            scene_changed=False,
        )

        updated_finding = CoreFinding.from_dict(legacy_finding.to_dict(include_state=True))
        return response_text, status, updated_finding


class LegacyReEvaluationEngineAdapter(ReEvaluationEnginePort):
    """Bridge re-evaluation port to legacy ``server.api.re_evaluate_finding``."""

    async def re_evaluate(
        self,
        *,
        client,
        finding: CoreFinding,
        updated_scene_text: str,
        model: str,
        max_tokens: int,
    ) -> dict:
        legacy_finding = Finding.from_dict(finding.to_dict(include_state=True))
        return await re_evaluate_finding(
            client,
            legacy_finding,
            updated_scene_text,
            model=model,
            max_tokens=max_tokens,
        )
