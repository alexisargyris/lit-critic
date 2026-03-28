"""Model-slot configuration and depth-mode resolution helpers.

Phase 2 foundation:
- persistent model slots (frontier/deep/quick)
- depth mode resolution (quick/deep)
"""

from __future__ import annotations

from typing import Mapping

from .config import DEFAULT_MODEL, is_known_model

SLOT_FRONTIER = "frontier"
SLOT_DEEP = "deep"
SLOT_QUICK = "quick"

ANALYSIS_MODE_QUICK = "quick"
ANALYSIS_MODE_DEEP = "deep"

VALID_ANALYSIS_MODES = {
    ANALYSIS_MODE_QUICK,
    ANALYSIS_MODE_DEEP,
}


def default_model_slots() -> dict[str, str]:
    quick_default = "haiku" if is_known_model("haiku") else DEFAULT_MODEL
    return {
        SLOT_FRONTIER: DEFAULT_MODEL,
        SLOT_DEEP: DEFAULT_MODEL,
        SLOT_QUICK: quick_default,
    }


def normalize_model_slots(raw: Mapping[str, str] | None) -> dict[str, str]:
    slots = default_model_slots()
    if not raw:
        return slots

    for key in (SLOT_FRONTIER, SLOT_DEEP, SLOT_QUICK):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            slots[key] = value.strip()
    return slots


def validate_model_slots(slots: Mapping[str, str]) -> dict[str, str]:
    normalized = normalize_model_slots(slots)
    for key, value in normalized.items():
        if not is_known_model(value):
            raise ValueError(f"Unknown model '{value}' for slot '{key}'")
    return normalized


def resolve_models_for_mode(mode: str, slots: Mapping[str, str] | None) -> dict[str, str]:
    resolved_mode = (mode or ANALYSIS_MODE_DEEP).strip().lower()
    if resolved_mode not in VALID_ANALYSIS_MODES:
        raise ValueError("mode must be one of: quick, deep")

    normalized_slots = validate_model_slots(normalize_model_slots(slots))
    frontier_model = normalized_slots[SLOT_FRONTIER]
    checker_model = (
        normalized_slots[SLOT_QUICK]
        if resolved_mode == ANALYSIS_MODE_QUICK
        else normalized_slots[SLOT_DEEP]
    )

    # Transitional behavior (Phase 2):
    # - analysis path uses checker-model resolution for quick/deep
    # - discussion remains on frontier
    return {
        "mode": resolved_mode,
        "frontier_model": frontier_model,
        "checker_model": checker_model,
        "analysis_model": checker_model,
        "discussion_model": frontier_model,
    }
