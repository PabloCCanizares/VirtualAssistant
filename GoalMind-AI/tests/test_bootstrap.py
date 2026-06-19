"""Tests para bootstrap.py: utilidades de entorno y carga del .env del proyecto."""

from __future__ import annotations

import os

import pytest

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


class TestLoadProjectEnv:
    """Cobertura de bootstrap.load_project_env (entrada al ciclo de vida de la app)."""

    def test_loads_variables_from_env_file_when_exists(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("BOOTSTRAP_TEST_FLAG=loaded_ok\n", encoding="utf-8")
        monkeypatch.delenv("BOOTSTRAP_TEST_FLAG", raising=False)

        bootstrap.load_project_env(tmp_path)

        assert os.environ.get("BOOTSTRAP_TEST_FLAG") == "loaded_ok"
        # Limpieza: dotenv escribe directamente sobre os.environ
        monkeypatch.delenv("BOOTSTRAP_TEST_FLAG", raising=False)

    def test_raises_runtime_error_when_env_missing(self, tmp_path):
        # tmp_path no contiene ningun .env
        with pytest.raises(RuntimeError, match=r"\.env"):
            bootstrap.load_project_env(tmp_path)

    def test_error_message_references_expected_path(self, tmp_path):
        try:
            bootstrap.load_project_env(tmp_path)
        except RuntimeError as exc:
            assert str(tmp_path / ".env") in str(exc)
        else:
            pytest.fail("load_project_env deberia haber lanzado RuntimeError")
