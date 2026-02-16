"""Core service ports for analysis/discussion/re-evaluation engines."""

from __future__ import annotations

from typing import Protocol

from .domain import CoreFinding


class AnalysisEnginePort(Protocol):
    """Port for running analysis over scene/index payload."""

    async def analyze(
        self,
        *,
        client,
        scene_text: str,
        indexes: dict[str, str],
        model: str,
        max_tokens: int,
    ) -> dict:
        ...


class DiscussionEnginePort(Protocol):
    """Port for handling one discussion turn against a finding."""

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
        ...


class ReEvaluationEnginePort(Protocol):
    """Port for re-evaluating stale findings against updated scene text."""

    async def re_evaluate(
        self,
        *,
        client,
        finding: CoreFinding,
        updated_scene_text: str,
        model: str,
        max_tokens: int,
    ) -> dict:
        ...
