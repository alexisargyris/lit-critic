"""
Configuration constants for the lit-critic system.
"""

import os

# Available models with their API identifiers, provider, and token limits
AVAILABLE_MODELS = {
    # --- Anthropic / Claude ---
    "opus":     {"id": "claude-opus-4-6",            "provider": "anthropic", "max_tokens": 8192, "label": "Opus 4.6 (deepest analysis)"},
    "opus-4-5": {"id": "claude-opus-4-5-20251101",   "provider": "anthropic", "max_tokens": 8192, "label": "Opus 4.5"},
    "sonnet":   {"id": "claude-sonnet-4-5-20250929",  "provider": "anthropic", "max_tokens": 4096, "label": "Sonnet 4.5 (balanced)"},
    "haiku":    {"id": "claude-haiku-4-5-20251001",   "provider": "anthropic", "max_tokens": 4096, "label": "Haiku 4.5 (fast & cheap)"},
    # --- OpenAI ---
    "gpt-4o":      {"id": "gpt-4o",      "provider": "openai", "max_tokens": 4096, "label": "GPT-4o (balanced)"},
    "gpt-4o-mini": {"id": "gpt-4o-mini", "provider": "openai", "max_tokens": 4096, "label": "GPT-4o Mini (fast & cheap)"},
    "o3":          {"id": "o3",           "provider": "openai", "max_tokens": 8192, "label": "o3 (reasoning)"},
}

DEFAULT_MODEL = "sonnet"

# Backward-compatible constants (resolve from default)
MODEL = AVAILABLE_MODELS[DEFAULT_MODEL]["id"]
MAX_TOKENS = AVAILABLE_MODELS[DEFAULT_MODEL]["max_tokens"]

# The coordinator merges findings from all 5 lenses into a single structured
# JSON.  Its output is typically much larger than an individual lens response,
# so it gets a dedicated (generous) token budget.  16 384 tokens can hold
# ~50-60 findings — more than any realistic scene review should produce.
COORDINATOR_MAX_TOKENS = 16_384

# Environment variable names for API keys, keyed by provider
API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
}


def resolve_model(name: str) -> dict:
    """Resolve a model short name to its config dict.
    
    Returns dict with keys: id, provider, max_tokens, label
    Raises ValueError if name is not recognised.
    """
    if name not in AVAILABLE_MODELS:
        valid = ", ".join(AVAILABLE_MODELS.keys())
        raise ValueError(f"Unknown model '{name}'. Available models: {valid}")
    return AVAILABLE_MODELS[name]


def resolve_api_key(provider: str, explicit_key: str | None = None) -> str:
    """Get the API key for a provider.

    Priority:
        1. ``explicit_key`` if provided (e.g. from CLI ``--api-key`` or request body).
        2. The provider's environment variable (``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY``).

    Raises ValueError if no key is found.
    """
    if explicit_key:
        return explicit_key

    env_var = API_KEY_ENV_VARS.get(provider)
    if env_var:
        key = os.environ.get(env_var)
        if key:
            return key

    raise ValueError(
        f"No API key for provider '{provider}'. "
        f"Pass --api-key or set the {API_KEY_ENV_VARS.get(provider, '???')} environment variable."
    )


INDEX_FILES = [
    "CANON.md",
    "CAST.md",
    "GLOSSARY.md",
    "STYLE.md",
    "THREADS.md",
    "TIMELINE.md",
]

OPTIONAL_FILES = [
    "LEARNING.md",
]

SESSION_FILE = ".lit-critic-session.json"
