"""Platform-facing analysis orchestration bridge.

This module provides a Platform import surface for analysis-related workflow
operations while legacy runtime pieces are still being phased out.
"""

from lit_platform.runtime.api import run_analysis, run_coordinator, run_coordinator_chunked, run_lens
from lit_platform.runtime.config import (
    API_KEY_ENV_VARS,
    AVAILABLE_MODELS,
    COORDINATOR_MAX_TOKENS,
    DEFAULT_MODEL,
    INDEX_FILES,
    MAX_TOKENS,
    MODEL,
    OPTIONAL_FILES,
    resolve_api_key,
    resolve_model,
)
from lit_platform.runtime.llm import create_client
from lit_platform.runtime.lens_preferences import (
    DEFAULT_LENS_PRESET,
    LENS_PRESETS,
    MAX_LENS_WEIGHT,
    MIN_LENS_WEIGHT,
    normalize_lens_preferences,
)

__all__ = [
    "INDEX_FILES",
    "OPTIONAL_FILES",
    "AVAILABLE_MODELS",
    "DEFAULT_MODEL",
    "API_KEY_ENV_VARS",
    "MODEL",
    "MAX_TOKENS",
    "COORDINATOR_MAX_TOKENS",
    "resolve_model",
    "resolve_api_key",
    "create_client",
    "run_lens",
    "run_coordinator",
    "run_coordinator_chunked",
    "run_analysis",
    "DEFAULT_LENS_PRESET",
    "LENS_PRESETS",
    "MIN_LENS_WEIGHT",
    "MAX_LENS_WEIGHT",
    "normalize_lens_preferences",
]
