from flask import Flask

from controllers.ai_chat_controller import ai_chat_bp


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(ai_chat_bp)
    return app.test_client()


def test_ai_chat_accepts_deep_search_mode_on(monkeypatch):
    captured = {}

    def _fake_run_chat(message, history, deep_search_mode=None):
        captured["message"] = message
        captured["history"] = history
        captured["deep_search_mode"] = deep_search_mode
        return "ok"

    monkeypatch.setattr("controllers.ai_chat_controller.run_chat", _fake_run_chat)
    client = _build_client()

    response = client.post(
        "/api/ai/chat",
        json={"message": "hola", "history": [], "deep_search_mode": "on"},
    )

    assert response.status_code == 200
    assert response.get_json()["reply"] == "ok"
    assert captured["deep_search_mode"] == "on"


def test_ai_chat_invalid_deep_search_mode_falls_back_to_auto(monkeypatch):
    captured = {}

    def _fake_run_chat(message, history, deep_search_mode=None):
        captured["deep_search_mode"] = deep_search_mode
        return "ok"

    monkeypatch.setattr("controllers.ai_chat_controller.run_chat", _fake_run_chat)
    client = _build_client()

    response = client.post(
        "/api/ai/chat",
        json={"message": "hola", "history": [], "deep_search_mode": "invalid"},
    )

    assert response.status_code == 200
    assert captured["deep_search_mode"] == "auto"


def test_ai_chat_omitted_deep_search_mode_keeps_none(monkeypatch):
    captured = {}

    def _fake_run_chat(message, history, deep_search_mode=None):
        captured["deep_search_mode"] = deep_search_mode
        return "ok"

    monkeypatch.setattr("controllers.ai_chat_controller.run_chat", _fake_run_chat)
    client = _build_client()

    response = client.post(
        "/api/ai/chat",
        json={"message": "hola", "history": []},
    )

    assert response.status_code == 200
    assert captured["deep_search_mode"] is None
