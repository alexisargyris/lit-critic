"""Platform orchestration facade that keeps FS/state concerns local."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.v1.schemas import (
    AnalyzeModelConfig,
    AnalyzeRequest,
    AnalyzeResponse,
    DiscussModelConfig,
    DiscussRequest,
    DiscussResponse,
    FindingContract,
    IndexesContract,
    ReEvaluateFindingRequest,
    ReEvaluateFindingResponse,
)

from .context import condense_discussion_context
from .core_client import CoreClient


class PlatformFacade:
    """Local orchestration facade that prepares payloads for stateless Core."""

    def __init__(self, *, core_client: CoreClient):
        self.core_client = core_client

    @staticmethod
    def load_scene_text(scene_path: Path) -> str:
        """Load scene text from local filesystem (Platform-owned concern)."""
        return scene_path.read_text(encoding="utf-8")

    @staticmethod
    def load_indexes_from_project(project_path: Path) -> IndexesContract:
        """Load local index files and convert to v1 indexes contract."""
        mapping = {
            "CANON": "CANON.md",
            "CAST": "CAST.md",
            "GLOSSARY": "GLOSSARY.md",
            "STYLE": "STYLE.md",
            "THREADS": "THREADS.md",
            "TIMELINE": "TIMELINE.md",
        }
        payload: dict[str, str | None] = {}
        for key, filename in mapping.items():
            path = project_path / filename
            payload[key] = path.read_text(encoding="utf-8") if path.exists() else None
        return IndexesContract.model_validate(payload)

    @staticmethod
    def load_legacy_indexes_from_project(
        project_path: Path,
        *,
        optional_filenames: tuple[str, ...] = (),
    ) -> dict[str, str]:
        """Load indexes in legacy ``*.md`` key shape expected by server prompts."""
        contract_indexes = PlatformFacade.load_indexes_from_project(project_path).model_dump()
        indexes = {f"{key}.md": (value or "") for key, value in contract_indexes.items()}

        for filename in optional_filenames:
            path = project_path / filename
            if path.exists():
                indexes[filename] = path.read_text(encoding="utf-8")

        return indexes

    def analyze_scene_text(
        self,
        *,
        scene_text: str,
        indexes: IndexesContract,
        analysis_model: str,
        api_keys: dict[str, str],
        max_tokens: int,
        learning_context: dict[str, Any] | None = None,
    ) -> AnalyzeResponse:
        """Prepare analyze request and call Core."""
        req = AnalyzeRequest(
            scene_text=scene_text,
            indexes=indexes,
            learning_context=learning_context,
            model_settings=AnalyzeModelConfig(
                analysis_model=analysis_model,
                api_keys=api_keys,
                max_tokens=max_tokens,
            ),
        )
        return self.core_client.analyze(req)

    def discuss_finding(
        self,
        *,
        scene_text: str,
        finding: FindingContract,
        author_message: str,
        discussion_turns: list[dict[str, Any]] | None,
        discussion_model: str,
        api_keys: dict[str, str],
        max_tokens: int,
    ) -> DiscussResponse:
        """Prepare condensed discussion payload and call Core."""
        discussion_context = condense_discussion_context(discussion_turns=discussion_turns)
        req = DiscussRequest(
            scene_text=scene_text,
            finding=finding,
            discussion_context=discussion_context,
            author_message=author_message,
            model_settings=DiscussModelConfig(
                discussion_model=discussion_model,
                api_keys=api_keys,
                max_tokens=max_tokens,
            ),
        )
        return self.core_client.discuss(req)

    def re_evaluate_finding(
        self,
        *,
        stale_finding: FindingContract,
        updated_scene_text: str,
        analysis_model: str,
        api_keys: dict[str, str],
        max_tokens: int,
        minimal_context: dict[str, Any] | None = None,
    ) -> ReEvaluateFindingResponse:
        """Prepare re-evaluate payload and call Core."""
        req = ReEvaluateFindingRequest(
            stale_finding=stale_finding,
            updated_scene_text=updated_scene_text,
            minimal_context=minimal_context,
            model_settings=AnalyzeModelConfig(
                analysis_model=analysis_model,
                api_keys=api_keys,
                max_tokens=max_tokens,
            ),
        )
        return self.core_client.re_evaluate(req)
