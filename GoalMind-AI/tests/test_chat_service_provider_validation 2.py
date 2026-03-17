from types import SimpleNamespace

import pytest

from ai.services.chat_service import run_chat


def test_run_chat_requires_groq_api_key(monkeypatch):
    settings = SimpleNamespace(
        llm_provider="groq",
        groq_api_key=None,
        gemini_api_key=None,
        openai_api_key="openai-key",
        groq_model="llama-test",
        gemini_model="gemini-test",
        openai_model="gpt-test",
        default_user_id="u1",
    )
    monkeypatch.setattr("ai.services.chat_service.get_settings", lambda: settings)

    with pytest.raises(ValueError, match="GROQ_API_KEY no configurada"):
        run_chat("hola", [])
