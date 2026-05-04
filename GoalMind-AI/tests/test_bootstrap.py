"""Tests para bootstrap.py: utilidades de entorno y logging."""

from __future__ import annotations

import logging

import bootstrap


class TestEnvBool:
    def test_returns_default_if_unset(self, monkeypatch):
        monkeypatch.delenv("F", raising=False)
        assert bootstrap.env_bool("F", default=True) is True
        assert bootstrap.env_bool("F", default=False) is False

    def test_truthy_strings(self, monkeypatch):
        for raw in ("1", "true", "yes", "on", "si", "sí", "TRUE", "Yes"):
            monkeypatch.setenv("F", raw)
            assert bootstrap.env_bool("F", default=False) is True, raw

    def test_falsy_strings(self, monkeypatch):
        for raw in ("0", "false", "no", "off", "", "  ", "lol"):
            monkeypatch.setenv("F", raw)
            assert bootstrap.env_bool("F", default=True) is False, raw


class TestEnvInt:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("N", raising=False)
        assert bootstrap.env_int("N", default=4) == 4

    def test_parses_value(self, monkeypatch):
        monkeypatch.setenv("N", "10")
        assert bootstrap.env_int("N", default=0) == 10

    def test_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("N", "ten")
        assert bootstrap.env_int("N", default=3) == 3

    def test_minimum_clamp(self, monkeypatch):
        monkeypatch.setenv("N", "0")
        assert bootstrap.env_int("N", default=5, minimum=2) == 2


class TestEnvironmentFlags:
    def test_is_production_default_false(self, monkeypatch):
        monkeypatch.delenv("FLASK_ENV", raising=False)
        assert bootstrap.is_production() is False

    def test_is_production_true_when_set(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "production")
        assert bootstrap.is_production() is True

    def test_is_production_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "  PRODUCTION  ")
        assert bootstrap.is_production() is True

    def test_is_debug_enabled_default_in_dev_is_true(self, monkeypatch):
        monkeypatch.delenv("FLASK_ENV", raising=False)
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        assert bootstrap.is_debug_enabled() is True

    def test_is_debug_enabled_default_in_production_is_false(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        assert bootstrap.is_debug_enabled() is False

    def test_is_debug_enabled_explicit_override(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.setenv("FLASK_DEBUG", "true")
        assert bootstrap.is_debug_enabled() is True


class TestSchedulerProcessGuard:
    def test_when_debug_disabled_starts(self, monkeypatch):
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        assert bootstrap.should_start_scheduler_process(debug_enabled=False) is True

    def test_when_debug_enabled_only_in_main_subprocess(self, monkeypatch):
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        assert bootstrap.should_start_scheduler_process(debug_enabled=True) is False
        monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
        assert bootstrap.should_start_scheduler_process(debug_enabled=True) is True


class TestConfigureLogging:
    def test_returns_logger_with_given_name(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        logger = bootstrap.configure_logging("my.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "NOPE")
        # No debe lanzar; usa INFO por defecto
        logger = bootstrap.configure_logging("test.fallback")
        assert isinstance(logger, logging.Logger)
