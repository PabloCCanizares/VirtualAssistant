"""Tests unitarios para ai.config: validadores de variables de entorno y dataclasses."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from ai import config as ai_config


def _model_settings(**overrides):
    values = {
        "llm_provider": "openai",
        "openai_api_key": "openai-key",
        "openai_model": "gpt-test",
        "gemini_api_key": None,
        "gemini_model": "gemini-test",
        "groq_api_key": None,
        "groq_model": "groq-test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "Yes", "on", "si", "sí"])
    def test_env_bool_truthy_values_return_true(self, monkeypatch, raw):
        monkeypatch.setenv("FLAG", raw)
        assert ai_config._env_bool("FLAG", default=False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "  ", "wat"])
    def test_env_bool_falsy_values_return_false(self, monkeypatch, raw):
        monkeypatch.setenv("FLAG", raw)
        assert ai_config._env_bool("FLAG", default=True) is False

    def test_env_bool_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("FLAG", raising=False)
        assert ai_config._env_bool("FLAG", default=True) is True
        assert ai_config._env_bool("FLAG", default=False) is False


class TestEnvInt:
    def test_env_int_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("X", raising=False)
        assert ai_config._env_int("X", default=7) == 7

    def test_env_int_parses_valid_integer(self, monkeypatch):
        monkeypatch.setenv("X", "42")
        assert ai_config._env_int("X", default=0) == 42

    def test_env_int_returns_default_when_invalid(self, monkeypatch):
        monkeypatch.setenv("X", "not-a-number")
        assert ai_config._env_int("X", default=5) == 5

    def test_env_int_clamps_below_minimum(self, monkeypatch):
        monkeypatch.setenv("X", "1")
        assert ai_config._env_int("X", default=0, minimum=10) == 10

    def test_env_int_clamps_above_maximum(self, monkeypatch):
        monkeypatch.setenv("X", "999")
        assert ai_config._env_int("X", default=0, maximum=100) == 100

    def test_env_int_within_bounds_returned_unchanged(self, monkeypatch):
        monkeypatch.setenv("X", "20")
        assert ai_config._env_int("X", default=0, minimum=10, maximum=30) == 20


class TestEnvChoice:
    def test_env_choice_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("PROVIDER", raising=False)
        assert ai_config._env_choice("PROVIDER", {"a", "b"}, default="a") == "a"

    def test_env_choice_returns_default_when_empty(self, monkeypatch):
        monkeypatch.setenv("PROVIDER", "   ")
        assert ai_config._env_choice("PROVIDER", {"a", "b"}, default="b") == "b"

    def test_env_choice_returns_value_when_in_allowed(self, monkeypatch):
        monkeypatch.setenv("PROVIDER", "a")
        assert ai_config._env_choice("PROVIDER", {"a", "b"}, default="b") == "a"

    def test_env_choice_lowercases_input(self, monkeypatch):
        monkeypatch.setenv("PROVIDER", "GEMINI")
        assert (
            ai_config._env_choice("PROVIDER", {"openai", "gemini"}, default="openai") == "gemini"
        )

    def test_env_choice_returns_default_when_not_allowed(self, monkeypatch):
        monkeypatch.setenv("PROVIDER", "claude")
        assert (
            ai_config._env_choice("PROVIDER", {"openai", "gemini"}, default="openai") == "openai"
        )


class TestEnvFloat:
    def test_env_float_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("Y", raising=False)
        assert ai_config._env_float("Y", default=0.5) == pytest.approx(0.5)

    def test_env_float_parses_valid_value(self, monkeypatch):
        monkeypatch.setenv("Y", "0.75")
        assert ai_config._env_float("Y", default=0.0) == pytest.approx(0.75)

    def test_env_float_returns_default_when_invalid(self, monkeypatch):
        monkeypatch.setenv("Y", "abc")
        assert ai_config._env_float("Y", default=0.3) == pytest.approx(0.3)

    def test_env_float_clamps_to_bounds(self, monkeypatch):
        monkeypatch.setenv("Y", "-1.5")
        assert ai_config._env_float("Y", default=0.0, minimum=0.0, maximum=1.0) == pytest.approx(0.0)
        monkeypatch.setenv("Y", "5.5")
        assert ai_config._env_float("Y", default=0.0, minimum=0.0, maximum=1.0) == pytest.approx(1.0)


class TestSettingsDataclass:
    def test_get_settings_returns_defaults_when_env_empty(self, monkeypatch):
        for key in (
            "LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL",
            "GEMINI_API_KEY", "GEMINI_MODEL", "GROQ_API_KEY", "GROQ_MODEL",
            "DEEP_SEARCH_ENABLED", "DEEP_SEARCH_PROVIDER", "DEEP_SEARCH_API_KEY",
            "DEEP_SEARCH_MODE_DEFAULT",
        ):
            monkeypatch.delenv(key, raising=False)
        # Evita cargar el .env real durante el test
        monkeypatch.setattr(ai_config, "load_env", lambda *a, **kw: None)

        settings = ai_config.get_settings()

        assert settings.llm_provider == "openai"
        assert settings.deep_search_enabled is False
        assert settings.deep_search_provider == "tavily"
        assert settings.deep_search_mode_default == "auto"
        assert settings.openai_model == "gpt-5-nano"

    def test_get_settings_picks_up_provider_override(self, monkeypatch):
        monkeypatch.setattr(ai_config, "load_env", lambda *a, **kw: None)
        monkeypatch.setenv("LLM_PROVIDER", "groq")

        settings = ai_config.get_settings()

        assert settings.llm_provider == "groq"

    def test_get_deep_search_config_propagates_settings(self, monkeypatch):
        monkeypatch.setattr(ai_config, "load_env", lambda *a, **kw: None)
        monkeypatch.setenv("DEEP_SEARCH_ENABLED", "true")
        monkeypatch.setenv("DEEP_SEARCH_PROVIDER", "serper")
        monkeypatch.setenv("DEEP_SEARCH_API_KEY", "abc-123")

        cfg = ai_config.get_deep_search_config()

        assert cfg.enabled is True
        assert cfg.provider == "serper"
        assert cfg.api_key == "abc-123"

    def test_settings_is_frozen_dataclass(self, monkeypatch):
        monkeypatch.setattr(ai_config, "load_env", lambda *a, **kw: None)
        settings = ai_config.get_settings()
        with pytest.raises(FrozenInstanceError):
            settings.llm_provider = "other"  # type: ignore[misc]


class TestChatModelCatalog:
    def test_catalog_exposes_availability_and_configured_default(self):
        catalog = ai_config.get_chat_model_catalog(
            _model_settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
            )
        )

        assert catalog["default_model_id"] == "gemini"
        assert [model["id"] for model in catalog["models"]] == [
            "openai",
            "gemini",
            "groq",
        ]
        assert [model["available"] for model in catalog["models"]] == [
            True,
            True,
            False,
        ]

    def test_catalog_falls_back_to_first_available_model(self):
        catalog = ai_config.get_chat_model_catalog(
            _model_settings(llm_provider="groq")
        )

        assert catalog["default_model_id"] == "openai"

    def test_resolve_supports_explicit_non_default_provider(self):
        option = ai_config.resolve_chat_model(
            _model_settings(gemini_api_key="gemini-key"),
            "gemini",
        )

        assert option.provider == "gemini"
        assert option.model == "gemini-test"

    def test_resolve_rejects_unknown_model(self):
        with pytest.raises(ValueError, match="Modelo no soportado"):
            ai_config.resolve_chat_model(_model_settings(), "unknown")

    def test_resolve_names_missing_provider_key(self):
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            ai_config.resolve_chat_model(_model_settings(), "groq")
