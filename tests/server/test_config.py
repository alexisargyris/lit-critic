"""
Tests for lit-critic.config module.
"""

import os
import pytest
from unittest.mock import patch

from server.config import (
    MODEL,
    MAX_TOKENS,
    COORDINATOR_MAX_TOKENS,
    INDEX_FILES,
    OPTIONAL_FILES,
    SESSION_FILE,
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    API_KEY_ENV_VARS,
    resolve_model,
    resolve_api_key,
)


class TestConfigConstants:
    """Tests for configuration constants."""
    
    def test_model_is_string(self):
        """MODEL should be a non-empty string."""
        assert isinstance(MODEL, str)
        assert len(MODEL) > 0
    
    def test_max_tokens_is_positive_integer(self):
        """MAX_TOKENS should be a positive integer."""
        assert isinstance(MAX_TOKENS, int)
        assert MAX_TOKENS > 0

    def test_coordinator_max_tokens_is_positive_integer(self):
        """COORDINATOR_MAX_TOKENS should be a positive integer."""
        assert isinstance(COORDINATOR_MAX_TOKENS, int)
        assert COORDINATOR_MAX_TOKENS > 0

    def test_coordinator_max_tokens_larger_than_lens(self):
        """Coordinator budget should be larger than the default lens budget."""
        assert COORDINATOR_MAX_TOKENS > MAX_TOKENS
    
    def test_index_files_is_list(self):
        """INDEX_FILES should be a non-empty list of strings."""
        assert isinstance(INDEX_FILES, list)
        assert len(INDEX_FILES) > 0
        assert all(isinstance(f, str) for f in INDEX_FILES)
    
    def test_index_files_are_markdown(self):
        """All INDEX_FILES should be .md files."""
        assert all(f.endswith('.md') for f in INDEX_FILES)
    
    def test_required_index_files_present(self):
        """Critical index files should be in the list."""
        required = ["CANON.md", "CAST.md", "GLOSSARY.md", "STYLE.md", "THREADS.md", "TIMELINE.md"]
        for filename in required:
            assert filename in INDEX_FILES, f"Missing required index file: {filename}"
    
    def test_optional_files_is_list(self):
        """OPTIONAL_FILES should be a list."""
        assert isinstance(OPTIONAL_FILES, list)
    
    def test_learning_md_in_optional(self):
        """LEARNING.md should be in optional files."""
        assert "LEARNING.md" in OPTIONAL_FILES
    
    def test_session_file_is_json(self):
        """SESSION_FILE should be a .json file."""
        assert isinstance(SESSION_FILE, str)
        assert SESSION_FILE.endswith('.json')
    
    def test_session_file_is_hidden(self):
        """SESSION_FILE should be a hidden file (starts with dot)."""
        assert SESSION_FILE.startswith('.')


class TestAvailableModels:
    """Tests for the AVAILABLE_MODELS registry."""

    def test_is_dict(self):
        """AVAILABLE_MODELS should be a non-empty dict."""
        assert isinstance(AVAILABLE_MODELS, dict)
        assert len(AVAILABLE_MODELS) > 0

    def test_default_model_exists(self):
        """DEFAULT_MODEL must be a key in AVAILABLE_MODELS."""
        assert DEFAULT_MODEL in AVAILABLE_MODELS

    def test_each_model_has_required_keys(self):
        """Every model entry must have id, provider, max_tokens, and label."""
        for name, cfg in AVAILABLE_MODELS.items():
            assert "id" in cfg, f"Model '{name}' missing 'id'"
            assert "provider" in cfg, f"Model '{name}' missing 'provider'"
            assert "max_tokens" in cfg, f"Model '{name}' missing 'max_tokens'"
            assert "label" in cfg, f"Model '{name}' missing 'label'"

    def test_max_tokens_positive(self):
        """Every model must have a positive max_tokens."""
        for name, cfg in AVAILABLE_MODELS.items():
            assert isinstance(cfg["max_tokens"], int), f"Model '{name}' max_tokens is not int"
            assert cfg["max_tokens"] > 0, f"Model '{name}' max_tokens must be positive"

    def test_anthropic_models_present(self):
        """At least one Anthropic model should be registered."""
        anthropic_models = [n for n, c in AVAILABLE_MODELS.items() if c["provider"] == "anthropic"]
        assert len(anthropic_models) >= 1

    def test_openai_models_present(self):
        """At least one OpenAI model should be registered."""
        openai_models = [n for n, c in AVAILABLE_MODELS.items() if c["provider"] == "openai"]
        assert len(openai_models) >= 1

    def test_known_providers(self):
        """All providers should be in the known set."""
        known = {"anthropic", "openai"}
        for name, cfg in AVAILABLE_MODELS.items():
            assert cfg["provider"] in known, f"Model '{name}' has unknown provider '{cfg['provider']}'"

    def test_default_model_is_anthropic(self):
        """Default model should be an Anthropic model (backward compat)."""
        assert AVAILABLE_MODELS[DEFAULT_MODEL]["provider"] == "anthropic"


class TestApiKeyEnvVars:
    """Tests for API_KEY_ENV_VARS mapping."""

    def test_is_dict(self):
        assert isinstance(API_KEY_ENV_VARS, dict)

    def test_anthropic_env_var(self):
        assert "anthropic" in API_KEY_ENV_VARS
        assert API_KEY_ENV_VARS["anthropic"] == "ANTHROPIC_API_KEY"

    def test_openai_env_var(self):
        assert "openai" in API_KEY_ENV_VARS
        assert API_KEY_ENV_VARS["openai"] == "OPENAI_API_KEY"


class TestResolveModel:
    """Tests for resolve_model()."""

    def test_resolve_known_model(self):
        """resolve_model should return the config dict for a known model."""
        result = resolve_model("sonnet")
        assert result["id"] == AVAILABLE_MODELS["sonnet"]["id"]
        assert result["provider"] == "anthropic"

    def test_resolve_openai_model(self):
        """resolve_model should work for OpenAI models."""
        result = resolve_model("gpt-4o")
        assert result["provider"] == "openai"
        assert result["id"] == "gpt-4o"

    def test_resolve_unknown_model(self):
        """resolve_model should raise ValueError for unknown model."""
        with pytest.raises(ValueError, match="Unknown model"):
            resolve_model("nonexistent-model-xyz")

    def test_resolve_returns_all_keys(self):
        """Resolved model dict should contain all required keys."""
        result = resolve_model(DEFAULT_MODEL)
        assert "id" in result
        assert "provider" in result
        assert "max_tokens" in result
        assert "label" in result


class TestResolveApiKey:
    """Tests for resolve_api_key()."""

    def test_explicit_key_takes_precedence(self):
        """An explicitly provided key should be returned directly."""
        key = resolve_api_key("anthropic", explicit_key="sk-test-123")
        assert key == "sk-test-123"

    def test_explicit_key_ignores_env(self):
        """Explicit key should be preferred even when env var is set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "from-env"}):
            key = resolve_api_key("anthropic", explicit_key="from-arg")
            assert key == "from-arg"

    def test_anthropic_from_env(self):
        """Should resolve from ANTHROPIC_API_KEY env var."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-env"}, clear=False):
            key = resolve_api_key("anthropic")
            assert key == "sk-ant-env"

    def test_openai_from_env(self):
        """Should resolve from OPENAI_API_KEY env var."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-oai-env"}, clear=False):
            key = resolve_api_key("openai")
            assert key == "sk-oai-env"

    def test_raises_when_no_key(self):
        """Should raise ValueError when no key is available."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env_clean, clear=True):
            with pytest.raises(ValueError, match="No API key"):
                resolve_api_key("anthropic")

    def test_raises_for_openai_without_key(self):
        """Should raise ValueError for OpenAI when no key is available."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env_clean, clear=True):
            with pytest.raises(ValueError, match="No API key"):
                resolve_api_key("openai")

    def test_error_message_includes_env_var_name(self):
        """Error message should mention the provider's env var."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env_clean, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                resolve_api_key("openai")
