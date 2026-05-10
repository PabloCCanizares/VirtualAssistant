"""Tests para bootstrap.py: utilidades de entorno."""

from __future__ import annotations

import bootstrap


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
