"""Tests para ai.services.chat_service: validacion de provider y resolucion de modos."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.services import chat_service


def _make_settings(**overrides):
    """Construye una pseudo-instancia de Settings con valores por defecto."""
    base = dict(
        llm_provider="openai",
        openai_api_key="sk-test",
        openai_model="gpt-test",
        gemini_api_key=None,
        gemini_model="gemini-test",
        groq_api_key=None,
        groq_model="groq-test",
        default_user_id=None,
        deep_search_enabled=False,
        deep_search_provider="tavily",
        deep_search_api_key=None,
        deep_search_max_results=5,
        deep_search_timeout_seconds=10,
        deep_search_max_sources=5,
        deep_search_mode_default="auto",
        deep_research_max_iterations=2,
        deep_research_max_tasks=2,
        deep_research_max_queries_per_task=2,
        deep_research_quality_threshold=0.5,
        deep_research_stagnation_limit=2,
        deep_research_loop_repeat_limit=1,
        deep_research_max_report_sources=3,
        deep_research_internal_source_limit=3,
        deep_research_parallel_queries=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestResolveDeepSearchMode:
    @pytest.mark.parametrize("requested", ["auto", "on", "off"])
    def test_valid_requested_mode_passes_through(self, requested):
        settings = _make_settings(deep_search_mode_default="auto")
        assert chat_service._resolve_deep_search_mode(settings, requested) == requested

    def test_normalizes_case_and_whitespace(self):
        settings = _make_settings(deep_search_mode_default="auto")
        assert chat_service._resolve_deep_search_mode(settings, "  ON  ") == "on"

    def test_uses_settings_default_when_requested_empty(self):
        settings = _make_settings(deep_search_mode_default="off")
        assert chat_service._resolve_deep_search_mode(settings, "") == "off"
        assert chat_service._resolve_deep_search_mode(settings, None) == "off"

    def test_invalid_mode_falls_back_to_auto(self):
        settings = _make_settings(deep_search_mode_default="auto")
        assert chat_service._resolve_deep_search_mode(settings, "ultra") == "auto"

    def test_invalid_default_in_settings_falls_back_to_auto(self):
        settings = _make_settings(deep_search_mode_default="garbage")
        assert chat_service._resolve_deep_search_mode(settings, None) == "auto"


class TestRunChatValidation:
    def test_run_chat_rejects_empty_message(self):
        with pytest.raises(ValueError, match="Mensaje vacio"):
            chat_service.run_chat("   ", history=[])

    def test_run_chat_rejects_none_message(self):
        with pytest.raises(ValueError, match="Mensaje vacio"):
            chat_service.run_chat(None, history=[])

    def test_run_chat_requires_openai_key_for_openai_provider(self, monkeypatch):
        monkeypatch.setattr(
            chat_service, "get_settings", lambda: _make_settings(llm_provider="openai", openai_api_key=None)
        )
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            chat_service.run_chat("hola", history=[])

    def test_run_chat_requires_gemini_key_for_gemini_provider(self, monkeypatch):
        monkeypatch.setattr(
            chat_service,
            "get_settings",
            lambda: _make_settings(llm_provider="gemini", gemini_api_key=None),
        )
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            chat_service.run_chat("hola", history=[])

    def test_run_chat_requires_groq_key_for_groq_provider(self, monkeypatch):
        monkeypatch.setattr(
            chat_service,
            "get_settings",
            lambda: _make_settings(llm_provider="groq", groq_api_key=None),
        )
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            chat_service.run_chat("hola", history=[])

    def test_run_chat_dispatches_to_graph_when_valid(self, monkeypatch, reset_pending_actions, reset_session_mutations):
        captured = {}

        def fake_run_graph_chat(**kwargs):
            captured.update(kwargs)
            return "respuesta del grafo"

        monkeypatch.setattr(
            chat_service,
            "get_settings",
            lambda: _make_settings(
                llm_provider="gemini",
                gemini_api_key="g-key",
                gemini_model="gemini-x",
                deep_search_enabled=True,
            ),
        )
        monkeypatch.setattr(chat_service, "run_graph_chat", fake_run_graph_chat)

        out = chat_service.run_chat("Hola, asistente", history=[{"role": "user", "content": "ping"}], deep_search_mode="on")

        assert out == "respuesta del grafo"
        assert captured["user_message"] == "Hola, asistente"
        assert captured["model"] == "gemini-x"
        assert captured["provider"] == "gemini"
        assert captured["deep_search_mode"] == "on"
        assert captured["deep_search_requested"] is True
        assert captured["deep_search_error"] == ""

    def test_run_chat_records_error_when_deep_search_disabled_but_requested(self, monkeypatch, reset_pending_actions, reset_session_mutations):
        captured = {}
        monkeypatch.setattr(
            chat_service,
            "get_settings",
            lambda: _make_settings(deep_search_enabled=False),
        )
        monkeypatch.setattr(
            chat_service,
            "run_graph_chat",
            lambda **kwargs: captured.update(kwargs) or "ok",
        )

        chat_service.run_chat("hola", history=None, deep_search_mode="on")

        assert captured["deep_search_mode"] == "on"
        assert captured["deep_search_requested"] is False
        assert "deshabilitado" in captured["deep_search_error"].lower()

    def test_run_chat_honors_explicit_model_selection(
        self,
        monkeypatch,
        reset_pending_actions,
        reset_session_mutations,
    ):
        captured = {}
        monkeypatch.setattr(
            chat_service,
            "get_settings",
            lambda: _make_settings(
                llm_provider="openai",
                gemini_api_key="gemini-key",
                gemini_model="gemini-selected",
            ),
        )
        monkeypatch.setattr(
            chat_service,
            "run_graph_chat",
            lambda **kwargs: captured.update(kwargs) or "ok",
        )

        chat_service.run_chat("hola", history=[], model_id="gemini")

        assert captured["provider"] == "gemini"
        assert captured["model"] == "gemini-selected"
