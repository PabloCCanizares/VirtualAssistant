from types import SimpleNamespace

from ai.services.chat_service import run_chat


def _mock_settings(**overrides):
    base = dict(
        llm_provider="openai",
        groq_api_key=None,
        gemini_api_key=None,
        openai_api_key="openai-key",
        groq_model="llama-test",
        gemini_model="gemini-test",
        openai_model="gpt-test",
        default_user_id="u1",
        deep_search_enabled=True,
        deep_search_mode_default="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_run_chat_propagates_deep_search_mode_from_request(monkeypatch):
    captured = {}

    monkeypatch.setattr("ai.services.chat_service.get_settings", lambda: _mock_settings())
    monkeypatch.setattr("ai.services.chat_service.get_user_context_json", lambda _user_id: "{}")
    monkeypatch.setattr("ai.services.chat_service.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("ai.services.chat_service.get_session_mutations_json", lambda _user_id: "[]")

    def _fake_run_graph_chat(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("ai.services.chat_service.run_graph_chat", _fake_run_graph_chat)

    reply = run_chat("hola", [], deep_search_mode="on")

    assert reply == "ok"
    assert captured["deep_search_mode"] == "on"
    assert captured["deep_search_requested"] is True
    assert captured["deep_search_error"] == ""


def test_run_chat_uses_default_mode_and_disabled_error(monkeypatch):
    captured = {}
    settings = _mock_settings(deep_search_enabled=False, deep_search_mode_default="on")

    monkeypatch.setattr("ai.services.chat_service.get_settings", lambda: settings)
    monkeypatch.setattr("ai.services.chat_service.get_user_context_json", lambda _user_id: "{}")
    monkeypatch.setattr("ai.services.chat_service.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("ai.services.chat_service.get_session_mutations_json", lambda _user_id: "[]")

    def _fake_run_graph_chat(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("ai.services.chat_service.run_graph_chat", _fake_run_graph_chat)

    reply = run_chat("hola", [], deep_search_mode=None)

    assert reply == "ok"
    assert captured["deep_search_mode"] == "on"
    assert captured["deep_search_requested"] is False
    assert captured["deep_search_error"] == "Deep search deshabilitado por configuración."


def test_run_chat_invalid_mode_falls_back_to_auto(monkeypatch):
    captured = {}

    monkeypatch.setattr("ai.services.chat_service.get_settings", lambda: _mock_settings())
    monkeypatch.setattr("ai.services.chat_service.get_user_context_json", lambda _user_id: "{}")
    monkeypatch.setattr("ai.services.chat_service.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("ai.services.chat_service.get_session_mutations_json", lambda _user_id: "[]")

    def _fake_run_graph_chat(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("ai.services.chat_service.run_graph_chat", _fake_run_graph_chat)

    reply = run_chat("hola", [], deep_search_mode="wrong-value")

    assert reply == "ok"
    assert captured["deep_search_mode"] == "auto"
    assert captured["deep_search_requested"] is False
