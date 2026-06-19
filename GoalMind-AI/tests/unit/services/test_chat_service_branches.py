"""Tests para `chat_service.run_chat` y ramas de error que faltan."""

from __future__ import annotations

import pytest

from ai.services import chat_service
from ai.services.chat_service import _resolve_deep_search_mode, run_chat, stream_chat
from tests._fakes import ScriptedLLM


class TestResolveDeepSearchMode:
    def test_empty_uses_default(self):
        class S:
            deep_search_mode_default = "auto"
        assert _resolve_deep_search_mode(S(), None) == "auto"
        assert _resolve_deep_search_mode(S(), "") == "auto"

    def test_valid_values_pass(self):
        class S:
            deep_search_mode_default = "auto"
        for mode in ("auto", "on", "off"):
            assert _resolve_deep_search_mode(S(), mode) == mode

    def test_invalid_falls_back_to_auto(self):
        class S:
            deep_search_mode_default = "auto"
        assert _resolve_deep_search_mode(S(), "invalido") == "auto"


class TestRunChat:
    def test_empty_message_raises(self):
        with pytest.raises(ValueError, match="Mensaje vacio"):
            run_chat("   ", [])

    def test_missing_openai_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        # setenv a "" en vez de delenv para evitar que load_dotenv() recargue del .env real.
        monkeypatch.setenv("OPENAI_API_KEY", "")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            run_chat("hola", [])

    def test_missing_gemini_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "")
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            run_chat("hola", [])

    def test_missing_groq_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "")
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            run_chat("hola", [])

    def test_run_chat_executes_graph(self, monkeypatch, patch_llm):
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": '{"category": "research"}',
            "agente de research": "notas",
            "agente writer": "respuesta final",
        })
        patch_llm(llm)
        out = run_chat("hola que tal", [])
        assert "respuesta final" in out


class TestStreamChat:
    def test_empty_message_raises(self):
        with pytest.raises(ValueError):
            list(stream_chat("   ", []))

    def test_stream_yields_events(self, monkeypatch, patch_llm):
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": '{"category": "research"}',
            "agente de research": "notas",
            "agente writer": "respuesta final",
        })
        patch_llm(llm)
        events = list(stream_chat("hola", []))
        assert any(e[0] == "done" for e in events)
