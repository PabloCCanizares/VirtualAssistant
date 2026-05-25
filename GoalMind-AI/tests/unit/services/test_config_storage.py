"""Bateria de `config/storage.py` (configuracion de subida de archivos)."""

from __future__ import annotations

import pytest
from flask import Flask

from bootstrap import env_int
from config.storage import DEFAULT_UPLOAD_EXTENSIONS, configure_storage


@pytest.fixture
def app():
    return Flask(__name__)


class TestConfigureStorage:
    def test_uses_defaults_when_env_unset(self, app, monkeypatch):
        monkeypatch.delenv("UPLOAD_ALLOWED_EXTENSIONS", raising=False)
        monkeypatch.delenv("MAX_CONTENT_LENGTH_MB", raising=False)
        configure_storage(app, env_int)
        assert app.config["UPLOAD_ALLOWED_EXTENSIONS"] == set(DEFAULT_UPLOAD_EXTENSIONS)
        # 25 MB por defecto
        assert app.config["MAX_CONTENT_LENGTH"] == 25 * 1024 * 1024

    def test_reads_extensions_from_env(self, app, monkeypatch):
        monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS", "pdf, txt , md")
        configure_storage(app, env_int)
        assert app.config["UPLOAD_ALLOWED_EXTENSIONS"] == {"pdf", "txt", "md"}

    def test_uses_max_content_length_from_env(self, app, monkeypatch):
        monkeypatch.setenv("MAX_CONTENT_LENGTH_MB", "10")
        configure_storage(app, env_int)
        assert app.config["MAX_CONTENT_LENGTH"] == 10 * 1024 * 1024

    def test_extensions_lowercased_and_stripped(self, app, monkeypatch):
        monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS", "PDF,  Docx ,,TXT")
        configure_storage(app, env_int)
        assert "pdf" in app.config["UPLOAD_ALLOWED_EXTENSIONS"]
        assert "docx" in app.config["UPLOAD_ALLOWED_EXTENSIONS"]
        # Las entradas vacias se filtran
        assert "" not in app.config["UPLOAD_ALLOWED_EXTENSIONS"]
