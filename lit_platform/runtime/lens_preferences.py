"""Lens preference presets, validation, and finding re-ranking utilities."""

from __future__ import annotations

from copy import deepcopy

LENS_NAMES = ("prose", "structure", "logic", "clarity", "continuity", "dialogue")

DEFAULT_LENS_PRESET = "auto"

LENS_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "prose": 1.0,
        "structure": 1.0,
        "logic": 1.0,
        "clarity": 1.0,
        "continuity": 1.0,
        "dialogue": 1.0,
    },
    "prose-first": {
        "prose": 1.6,
        "structure": 1.1,
        "logic": 0.9,
        "clarity": 0.9,
        "continuity": 0.8,
        "dialogue": 1.1,
    },
    "story-logic": {
        "prose": 0.8,
        "structure": 1.4,
        "logic": 1.5,
        "clarity": 1.0,
        "continuity": 1.2,
        "dialogue": 1.1,
    },
    "clarity-pass": {
        "prose": 0.8,
        "structure": 1.0,
        "logic": 1.2,
        "clarity": 1.6,
        "continuity": 1.1,
        "dialogue": 1.3,
    },
    "single-scene": {
        "prose": 1.5,
        "structure": 0.8,
        "logic": 1.3,
        "clarity": 1.3,
        "continuity": 0.7,
        "dialogue": 1.4,
    },
    "multi-scene": {
        "prose": 0.8,
        "structure": 1.5,
        "logic": 1.3,
        "clarity": 1.2,
        "continuity": 1.5,
        "dialogue": 0.7,
    },
}

MIN_LENS_WEIGHT = 0.0
MAX_LENS_WEIGHT = 3.0


def default_lens_preferences() -> dict:
    """Return a fresh default lens preferences payload."""
    default_weights_preset = "balanced" if DEFAULT_LENS_PRESET == "auto" else DEFAULT_LENS_PRESET
    return {
        "preset": DEFAULT_LENS_PRESET,
        "weights": deepcopy(LENS_PRESETS[default_weights_preset]),
    }


def resolve_auto_preset(scene_count: int) -> str:
    """Resolve the 'auto' preset to a concrete preset name."""
    if scene_count <= 1:
        return "single-scene"
    return "multi-scene"


def normalize_lens_preferences(raw: dict | None) -> dict:
    """Validate and normalize user-provided lens preferences.

    Accepted shape:
        {
          "preset": "balanced" | "prose-first" | "story-logic" | "clarity-pass",
          "weights": {"prose": 1.2, ...}
        }
    """
    prefs = default_lens_preferences()
    if not raw:
        return prefs

    preset = raw.get("preset", DEFAULT_LENS_PRESET)
    resolved_preset = "balanced" if preset == "auto" else preset
    if resolved_preset not in LENS_PRESETS:
        valid = ", ".join(sorted(LENS_PRESETS.keys()))
        raise ValueError(f"Invalid lens preset '{resolved_preset}'. Valid presets: {valid}")

    weights = deepcopy(LENS_PRESETS[resolved_preset])
    overrides = raw.get("weights") or {}
    if not isinstance(overrides, dict):
        raise ValueError("lens_preferences.weights must be an object mapping lens names to numbers")

    for lens_name, weight in overrides.items():
        if lens_name not in LENS_NAMES:
            valid = ", ".join(LENS_NAMES)
            raise ValueError(f"Unknown lens '{lens_name}' in lens preferences. Valid lenses: {valid}")
        try:
            weight_value = float(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid weight for lens '{lens_name}': {weight!r}") from exc

        if weight_value < MIN_LENS_WEIGHT or weight_value > MAX_LENS_WEIGHT:
            raise ValueError(
                f"Weight for lens '{lens_name}' must be between {MIN_LENS_WEIGHT} and {MAX_LENS_WEIGHT}"
            )
        weights[lens_name] = weight_value

    return {
        "preset": resolved_preset,
        "weights": weights,
    }


def rerank_coordinated_findings(coordinated: dict, lens_preferences: dict) -> dict:
    """Apply deterministic re-ranking based on severity and lens weights."""
    findings = coordinated.get("findings") or []
    if not findings:
        return coordinated

    weights = (lens_preferences or {}).get("weights") or {}
    severity_base = {
        "critical": 100,
        "major": 30,
        "minor": 10,
    }

    def _weight_for_finding(finding: dict) -> float:
        flagged_by = finding.get("flagged_by") or []
        if flagged_by:
            values = [weights.get(l, 1.0) for l in flagged_by]
            return max(values) if values else 1.0
        return weights.get(finding.get("lens", ""), 1.0)

    decorated = []
    for idx, finding in enumerate(findings):
        sev = str(finding.get("severity", "minor")).lower().strip()
        base = severity_base.get(sev, severity_base["major"])
        score = base * _weight_for_finding(finding)
        decorated.append((idx, score, finding))

    decorated.sort(key=lambda item: (-item[1], item[0]))

    reranked = []
    for number, (_, _, finding) in enumerate(decorated, start=1):
        updated = dict(finding)
        updated["number"] = number
        reranked.append(updated)

    coordinated["findings"] = reranked
    return coordinated
