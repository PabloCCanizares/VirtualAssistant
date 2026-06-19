"""Bateria completa del controlador REST de configuracion.

Cubre las 5 rutas: lectura de ajustes, aplicacion con validacion, pruebas
de conexion a MongoDB local y remoto, y sincronizacion manual. Tambien se
ejercita el helper `_validate_api_keys` para los tres proveedores.

Se monkeypatchean las dependencias externas: `set_key` (dotenv) no escribe
en disco, `MongoClient` no abre sockets, los clientes de OpenAI/Gemini/Groq
se sustituyen por dobles que devuelven listas vacias o lanzan excepciones
segun el caso.
"""

from __future__ import annotations

import pytest
from flask import Flask

from controllers import config_controller
from controllers.config_controller import config_bp


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    # set_key: no escribir en disco real
    monkeypatch.setattr(config_controller, "set_key", lambda *a, **k: True)
    # reconnect_databases: por defecto, exito sin errores
    monkeypatch.setattr(
        config_controller, "reconnect_databases", lambda: {"errors": []}
    )
    app.register_blueprint(config_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# GET /config/api/settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    def test_returns_schema_and_current_values(self, client, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        resp = client.get("/config/api/settings")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "sections" in body
        assert "schema" in body
        assert body["sections"]["ai"]["LLM_PROVIDER"] == "gemini"


# ---------------------------------------------------------------------------
# POST /config/api/apply
# ---------------------------------------------------------------------------


class TestApplySettings:
    def test_empty_payload_returns_400(self, client):
        resp = client.post("/config/api/apply", json={})
        assert resp.status_code == 400
        assert "_global" in resp.get_json()["errors"]

    def test_unknown_key_returns_400(self, client):
        resp = client.post("/config/api/apply", json={"NOT_A_KEY": "x"})
        assert resp.status_code == 400
        assert "NOT_A_KEY" in resp.get_json()["errors"]

    def test_invalid_select_value(self, client):
        resp = client.post("/config/api/apply", json={"LLM_PROVIDER": "invalid"})
        assert resp.status_code == 400
        assert "LLM_PROVIDER" in resp.get_json()["errors"]

    def test_invalid_number_value(self, client):
        resp = client.post(
            "/config/api/apply",
            json={"DEEP_SEARCH_MAX_RESULTS": "no-numero"},
        )
        assert resp.status_code == 400
        assert "DEEP_SEARCH_MAX_RESULTS" in resp.get_json()["errors"]

    def test_number_below_min(self, client):
        resp = client.post(
            "/config/api/apply", json={"DEEP_SEARCH_MAX_RESULTS": "0"}
        )
        assert resp.status_code == 400

    def test_number_above_max(self, client):
        resp = client.post(
            "/config/api/apply", json={"DEEP_SEARCH_MAX_RESULTS": "999"}
        )
        assert resp.status_code == 400

    def test_apply_valid_settings(self, client):
        resp = client.post(
            "/config/api/apply", json={"LLM_PROVIDER": "openai", "OPENAI_MODEL": "gpt-4"}
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["restart_required"] is False

    def test_restart_required_when_changing_flask_debug(self, client):
        resp = client.post("/config/api/apply", json={"FLASK_DEBUG": "0"})
        assert resp.status_code == 200
        assert resp.get_json()["restart_required"] is True

    def test_mongo_reconnect_with_errors_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(
            config_controller, "reconnect_databases",
            lambda: {"errors": ["MONGO_LOCAL_URI: timeout"]},
        )
        resp = client.post(
            "/config/api/apply",
            json={"MONGO_LOCAL_URI": "mongodb://bad-host:27017"},
        )
        assert resp.status_code == 400
        assert "MONGO_LOCAL_URI" in resp.get_json()["errors"]

    def test_invalid_openai_key_rollback(self, client, monkeypatch):
        class _FakeOpenAI:
            def __init__(self, api_key):
                self.models = self

            def list(self):
                raise RuntimeError("invalid key")

        monkeypatch.setattr(config_controller, "OpenAI", _FakeOpenAI)
        resp = client.post("/config/api/apply", json={"OPENAI_API_KEY": "sk-bad"})
        assert resp.status_code == 400
        assert "OPENAI_API_KEY" in resp.get_json()["errors"]

    def test_valid_openai_key_succeeds(self, client, monkeypatch):
        class _FakeOpenAI:
            def __init__(self, api_key):
                self.models = self

            def list(self):
                return []

        monkeypatch.setattr(config_controller, "OpenAI", _FakeOpenAI)
        resp = client.post("/config/api/apply", json={"OPENAI_API_KEY": "sk-good"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /config/api/test-mongo-local
# ---------------------------------------------------------------------------


class TestMongoLocal:
    def test_empty_uri_returns_400(self, client):
        resp = client.post("/config/api/test-mongo-local", json={"uri": ""})
        assert resp.status_code == 400

    def test_wrong_scheme_returns_400(self, client):
        resp = client.post(
            "/config/api/test-mongo-local",
            json={"uri": "mongodb+srv://x"},
        )
        assert resp.status_code == 400

    def test_successful_connection(self, client, monkeypatch):
        class _FakeClient:
            def __init__(self, *a, **k):
                self.admin = self

            def command(self, name):
                return {}

            def close(self):
                pass

        monkeypatch.setattr(config_controller, "MongoClient", _FakeClient)
        resp = client.post(
            "/config/api/test-mongo-local",
            json={"uri": "mongodb://localhost:27017"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_connection_failure(self, client, monkeypatch):
        def _factory(*a, **k):
            raise RuntimeError("conexion fallida")

        monkeypatch.setattr(config_controller, "MongoClient", _factory)
        resp = client.post(
            "/config/api/test-mongo-local",
            json={"uri": "mongodb://bad-host"},
        )
        assert resp.status_code == 400
        assert "fallida" in resp.get_json()["message"]


# ---------------------------------------------------------------------------
# POST /config/api/test-mongo-remote
# ---------------------------------------------------------------------------


class TestMongoRemote:
    def test_empty_uri_returns_400(self, client):
        resp = client.post("/config/api/test-mongo-remote", json={"uri": ""})
        assert resp.status_code == 400

    def test_wrong_scheme_returns_400(self, client):
        resp = client.post(
            "/config/api/test-mongo-remote",
            json={"uri": "mongodb://localhost"},
        )
        assert resp.status_code == 400

    def test_successful_connection(self, client, monkeypatch):
        class _FakeClient:
            def __init__(self, *a, **k):
                self.admin = self

            def command(self, name):
                return {}

            def close(self):
                pass

        monkeypatch.setattr(config_controller, "MongoClient", _FakeClient)
        resp = client.post(
            "/config/api/test-mongo-remote",
            json={"uri": "mongodb+srv://atlas-host"},
        )
        assert resp.status_code == 200

    def test_connection_failure(self, client, monkeypatch):
        def _factory(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(config_controller, "MongoClient", _factory)
        resp = client.post(
            "/config/api/test-mongo-remote",
            json={"uri": "mongodb+srv://bad"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /config/api/sync-now
# ---------------------------------------------------------------------------


class TestSyncNow:
    def test_returns_503_when_no_remote(self, client, monkeypatch):
        monkeypatch.setattr(
            config_controller, "ensure_remote_connection", lambda app=None: False
        )
        resp = client.post("/config/api/sync-now")
        assert resp.status_code == 503

    def test_full_sync_success(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(
            config_controller, "ensure_remote_connection", lambda app=None: True
        )
        monkeypatch.setattr(
            config_controller, "flush_deletion_queue",
            lambda: calls.append("flush") or 1,
        )
        monkeypatch.setattr(
            config_controller, "sync_all_collections",
            lambda: calls.append("pull") or 1,
        )
        monkeypatch.setattr(
            config_controller, "sync_local_to_remote",
            lambda: calls.append("push") or 1,
        )

        # Stub para ProjectDocumentModel.promote_pending_remote_uploads
        from model.project_document_model import ProjectDocumentModel
        monkeypatch.setattr(
            ProjectDocumentModel, "promote_pending_remote_uploads",
            staticmethod(lambda app=None: calls.append("promote") or 0),
        )

        resp = client.post("/config/api/sync-now")
        assert resp.status_code == 200
        assert calls == ["flush", "promote", "pull", "push"]

    def test_sync_with_exception_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(
            config_controller, "ensure_remote_connection", lambda app=None: True
        )

        def _boom():
            raise RuntimeError("fail")

        monkeypatch.setattr(config_controller, "flush_deletion_queue", _boom)
        resp = client.post("/config/api/sync-now")
        assert resp.status_code == 500
        assert "fail" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Validacion de API keys (helper privado)
# ---------------------------------------------------------------------------


class TestValidateApiKeys:
    def test_openai_missing_library(self, monkeypatch):
        monkeypatch.setattr(config_controller, "OpenAI", None)
        errors = config_controller._validate_api_keys(
            {"OPENAI_API_KEY": "sk-x"}, {"OPENAI_API_KEY"}
        )
        assert "dependencia" in errors["OPENAI_API_KEY"]

    def test_groq_missing_library(self, monkeypatch):
        monkeypatch.setattr(config_controller, "Groq", None)
        errors = config_controller._validate_api_keys(
            {"GROQ_API_KEY": "k"}, {"GROQ_API_KEY"}
        )
        assert "dependencia" in errors["GROQ_API_KEY"]

    def test_gemini_missing_library(self, monkeypatch):
        monkeypatch.setattr(config_controller, "genai", None)
        errors = config_controller._validate_api_keys(
            {"GEMINI_API_KEY": "k"}, {"GEMINI_API_KEY"}
        )
        assert "dependencia" in errors["GEMINI_API_KEY"]

    def test_empty_keys_are_skipped(self, monkeypatch):
        # No se invoca al SDK cuando la clave esta vacia.
        errors = config_controller._validate_api_keys(
            {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GROQ_API_KEY": ""},
            {"OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"},
        )
        assert errors == {}
