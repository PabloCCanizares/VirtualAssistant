"""Tests para invoke_with_retry: politica de reintentos y backoff de invocacion al LLM."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.services import llm_utils
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry


class _FakeLLM:
    """LLM falso que ejecuta una secuencia de respuestas/errores."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(content=item)


class TestInvokeWithRetry:
    def test_returns_content_on_first_attempt(self, monkeypatch):
        monkeypatch.setattr(llm_utils.time, "sleep", lambda *_: None)
        llm = _FakeLLM(["  hola  "])
        assert invoke_with_retry(llm, [], retries=2) == "hola"
        assert llm.calls == 1

    def test_retries_until_success(self, monkeypatch):
        sleep_calls = []
        monkeypatch.setattr(llm_utils.time, "sleep", lambda s: sleep_calls.append(s))
        llm = _FakeLLM([RuntimeError("boom"), "ok"])

        result = invoke_with_retry(llm, [], retries=1, backoff_seconds=0.01)

        assert result == "ok"
        assert llm.calls == 2
        assert sleep_calls == [0.01]  # backoff exponencial: 0.01 * 2**0

    def test_raises_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setattr(llm_utils.time, "sleep", lambda *_: None)
        llm = _FakeLLM([RuntimeError("a"), RuntimeError("b"), RuntimeError("c")])

        with pytest.raises(LLMInvokeError):
            invoke_with_retry(llm, [], retries=2)
        assert llm.calls == 3

    def test_handles_none_content_gracefully(self, monkeypatch):
        monkeypatch.setattr(llm_utils.time, "sleep", lambda *_: None)
        llm = _FakeLLM([None])
        # response.content puede ser None segun el provider
        # con `(response.content or "").strip()` debe devolver ""
        assert invoke_with_retry(llm, []) == ""

    def test_zero_retries_means_one_attempt(self, monkeypatch):
        monkeypatch.setattr(llm_utils.time, "sleep", lambda *_: None)
        llm = _FakeLLM([RuntimeError("only-one")])
        with pytest.raises(LLMInvokeError):
            invoke_with_retry(llm, [], retries=0)
        assert llm.calls == 1

    def test_negative_retries_is_treated_as_one_attempt(self, monkeypatch):
        monkeypatch.setattr(llm_utils.time, "sleep", lambda *_: None)
        llm = _FakeLLM(["respuesta"])
        # retries=-5 produce attempts = max(1, -4) = 1
        assert invoke_with_retry(llm, [], retries=-5) == "respuesta"
        assert llm.calls == 1
