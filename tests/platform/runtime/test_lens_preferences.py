"""Unit tests for lens preference presets and reranking behavior."""

from copy import deepcopy

from lit_platform.runtime.lens_preferences import (
    LENS_PRESETS,
    normalize_lens_preferences,
    rerank_coordinated_findings,
    resolve_auto_preset,
)


def test_resolve_auto_preset_by_scene_count():
    assert resolve_auto_preset(0) == "single-scene"
    assert resolve_auto_preset(1) == "single-scene"
    assert resolve_auto_preset(2) == "multi-scene"
    assert resolve_auto_preset(5) == "multi-scene"


def test_normalize_lens_preferences_accepts_single_scene_preset():
    normalized = normalize_lens_preferences({"preset": "single-scene"})

    assert normalized["preset"] == "single-scene"
    assert normalized["weights"] == LENS_PRESETS["single-scene"]


def test_normalize_lens_preferences_accepts_multi_scene_preset():
    normalized = normalize_lens_preferences({"preset": "multi-scene"})

    assert normalized["preset"] == "multi-scene"
    assert normalized["weights"] == LENS_PRESETS["multi-scene"]


def test_normalize_lens_preferences_auto_falls_back_to_balanced_without_scene_context():
    normalized = normalize_lens_preferences({"preset": "auto"})

    assert normalized["preset"] == "balanced"
    assert normalized["weights"] == LENS_PRESETS["balanced"]


def test_rerank_coordinated_findings_prefers_prose_in_single_scene_preset():
    coordinated = {
        "findings": [
            {
                "number": 1,
                "severity": "major",
                "lens": "structure",
                "location": "L10",
                "evidence": "structure issue",
                "impact": "impact",
                "options": ["option"],
                "flagged_by": ["structure"],
            },
            {
                "number": 2,
                "severity": "major",
                "lens": "prose",
                "location": "L20",
                "evidence": "prose issue",
                "impact": "impact",
                "options": ["option"],
                "flagged_by": ["prose"],
            },
        ]
    }

    reranked = rerank_coordinated_findings(
        deepcopy(coordinated),
        {"preset": "single-scene", "weights": LENS_PRESETS["single-scene"]},
    )

    assert reranked["findings"][0]["lens"] == "prose"
    assert reranked["findings"][1]["lens"] == "structure"


def test_rerank_coordinated_findings_prefers_structure_in_multi_scene_preset():
    coordinated = {
        "findings": [
            {
                "number": 1,
                "severity": "major",
                "lens": "prose",
                "location": "L10",
                "evidence": "prose issue",
                "impact": "impact",
                "options": ["option"],
                "flagged_by": ["prose"],
            },
            {
                "number": 2,
                "severity": "major",
                "lens": "structure",
                "location": "L20",
                "evidence": "structure issue",
                "impact": "impact",
                "options": ["option"],
                "flagged_by": ["structure"],
            },
        ]
    }

    reranked = rerank_coordinated_findings(
        deepcopy(coordinated),
        {"preset": "multi-scene", "weights": LENS_PRESETS["multi-scene"]},
    )

    assert reranked["findings"][0]["lens"] == "structure"
    assert reranked["findings"][1]["lens"] == "prose"