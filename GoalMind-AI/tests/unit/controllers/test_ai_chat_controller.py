"""Bateria del controlador del chat con el asistente.

La ruta `/api/ai/chat` (SSE) esta cubierta en `tests/integration/test_sse_stream.py`.
Aqui se completan la ruta `/api/ai/summarize-document` y los caminos de validacion
que faltan, asi como el helper `_normalize_deep_search_mode`.
"""

from __future__ import annotations

import pytest
from flask import Flask

from controllers import ai_chat_controller
from controllers.ai_chat_controller import ai_chat_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = "test"
    app.config["TESTING"] = True
    app.register_blueprint(ai_chat_bp)
    return app.test_client()


class TestNormalizeDeepSearchMode:
    def test_empty_returns_none(self):
        assert ai_chat_controller._normalize_deep_search_mode("") is None
        assert ai_chat_controller._normalize_deep_search_mode(None) is None
        assert ai_chat_controller._normalize_deep_search_mode("   ") is None

    def test_valid_modes_pass_through(self):
        for mode in ("auto", "on", "off"):
            assert ai_chat_controller._normalize_deep_search_mode(mode) == mode
            assert ai_chat_controller._normalize_deep_search_mode(mode.upper()) == mode

    def test_invalid_mode_defaults_to_auto(self):
        assert ai_chat_controller._normalize_deep_search_mode("invalid") == "auto"


class TestSummarizeDocument:
    def test_missing_doc_id_returns_400(self, client):
        resp = client.post(
            "/api/ai/summarize-document",
            json={"project_id": "abc"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_missing_project_id_returns_400(self, client):
        resp = client.post(
            "/api/ai/summarize-document",
            json={"doc_id": "abc"},
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post("/api/ai/summarize-document", json={})
        assert resp.status_code == 400

    def test_success_returns_message(self, client, monkeypatch):
        # Stub completo de summarize_and_save_note (import perezoso dentro
        # de la ruta).
        from ai.services import doc_summarize_service

        monkeypatch.setattr(
            doc_summarize_service, "summarize_and_save_note",
            lambda doc_id, project_id: "Resumen guardado",
        )
        resp = client.post(
            "/api/ai/summarize-document",
            json={"doc_id": "doc1", "project_id": "proj1"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["message"] == "Resumen guardado"

    def test_value_error_returns_404(self, client, monkeypatch):
        from ai.services import doc_summarize_service

        def _missing(doc_id, project_id):
            raise ValueError("Documento no encontrado")

        monkeypatch.setattr(doc_summarize_service, "summarize_and_save_note", _missing)
        resp = client.post(
            "/api/ai/summarize-document",
            json={"doc_id": "x", "project_id": "y"},
        )
        assert resp.status_code == 404
        assert "no encontrado" in resp.get_json()["message"].lower()

    def test_unexpected_exception_returns_500(self, client, monkeypatch):
        from ai.services import doc_summarize_service

        def _boom(doc_id, project_id):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(doc_summarize_service, "summarize_and_save_note", _boom)
        resp = client.post(
            "/api/ai/summarize-document",
            json={"doc_id": "x", "project_id": "y"},
        )
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False
