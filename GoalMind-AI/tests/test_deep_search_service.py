"""Tests para deep_search_service: normalizacion, deduplicado y orquestacion por proveedor."""

from __future__ import annotations

import pytest

from ai.config import DeepSearchConfig
from ai.services import deep_search_service as dss
from ai.services.deep_search_service import (
    DeepSearchError,
    _dedupe_by_url,
    _normalize_result,
    deep_search,
)


def _config(**overrides):
    base = dict(
        enabled=True,
        provider="tavily",
        api_key="test-key",
        max_results=5,
        timeout_seconds=10,
        max_sources=5,
        mode_default="on",
    )
    base.update(overrides)
    return DeepSearchConfig(**base)


class TestNormalizeResult:
    def test_returns_none_when_url_missing(self):
        assert (
            _normalize_result(
                title="x", url="", snippet="s", score=0.5, provider="tavily", raw={}
            )
            is None
        )

    def test_strips_whitespace(self):
        out = _normalize_result(
            title="  Hola  ",
            url="  https://example.com  ",
            snippet="  cuerpo  ",
            score=0.9,
            provider="tavily",
            raw={},
        )
        assert out["title"] == "Hola"
        assert out["url"] == "https://example.com"
        assert out["snippet"] == "cuerpo"

    def test_uses_url_as_title_when_title_empty(self):
        out = _normalize_result(
            title="", url="https://example.com", snippet="", score=None, provider="tavily", raw={}
        )
        assert out["title"] == "https://example.com"

    def test_score_falls_back_to_zero_when_invalid(self):
        out = _normalize_result(
            title="t", url="https://x", snippet="", score="not-a-number",  # type: ignore[arg-type]
            provider="tavily", raw={"x": 1},
        )
        assert out["score"] == 0.0
        assert out["raw"] == {"x": 1}

    def test_provider_label_preserved(self):
        out = _normalize_result(
            title="t", url="https://x", snippet="", score=1, provider="brave", raw={}
        )
        assert out["provider"] == "brave"


class TestDedupeByUrl:
    def test_empty_input_returns_empty(self):
        assert _dedupe_by_url([]) == []

    def test_drops_entries_without_url(self):
        results = [
            {"url": "", "score": 0.9},
            {"url": "  ", "score": 0.5},
            {"url": "https://a", "score": 0.3},
        ]
        deduped = _dedupe_by_url(results)
        assert len(deduped) == 1
        assert deduped[0]["url"] == "https://a"

    def test_keeps_highest_scoring_duplicate(self):
        results = [
            {"url": "https://a", "score": 0.4},
            {"url": "https://a", "score": 0.9},
            {"url": "https://a", "score": 0.7},
        ]
        deduped = _dedupe_by_url(results)
        assert len(deduped) == 1
        assert deduped[0]["score"] == 0.9

    def test_sorts_descending_by_score(self):
        results = [
            {"url": "https://a", "score": 0.3},
            {"url": "https://b", "score": 0.9},
            {"url": "https://c", "score": 0.6},
        ]
        deduped = _dedupe_by_url(results)
        assert [r["url"] for r in deduped] == ["https://b", "https://c", "https://a"]


class TestDeepSearchDispatcher:
    def test_empty_query_returns_empty_list(self):
        assert deep_search("", config=_config()) == []
        assert deep_search("   ", config=_config()) == []

    def test_disabled_config_raises(self):
        with pytest.raises(DeepSearchError, match="deshabilitado"):
            deep_search("python", config=_config(enabled=False))

    def test_missing_api_key_raises(self):
        with pytest.raises(DeepSearchError, match="DEEP_SEARCH_API_KEY"):
            deep_search("python", config=_config(api_key=""))

    def test_unknown_provider_raises(self):
        with pytest.raises(DeepSearchError, match="no soportado"):
            deep_search("python", config=_config(provider="unknown"))

    def test_provider_handler_invoked_and_results_truncated_to_max(self, monkeypatch):
        results = [
            {"url": f"https://a/{i}", "title": f"t-{i}", "snippet": "", "score": 1.0 - i * 0.01, "provider": "tavily", "raw": {}}
            for i in range(10)
        ]
        monkeypatch.setitem(dss.PROVIDER_HANDLERS, "tavily", lambda q, cfg: results)

        out = deep_search("python", config=_config(max_results=3))

        assert len(out) == 3
        # ordenados desc por score (todos diferentes)
        assert out[0]["url"] == "https://a/0"
        assert out[1]["url"] == "https://a/1"
        assert out[2]["url"] == "https://a/2"

    def test_unexpected_handler_exception_wrapped(self, monkeypatch):
        def boom(q, cfg):
            raise RuntimeError("network down")

        monkeypatch.setitem(dss.PROVIDER_HANDLERS, "tavily", boom)
        with pytest.raises(DeepSearchError, match="No se pudo completar"):
            deep_search("python", config=_config())

    def test_deep_search_error_passes_through(self, monkeypatch):
        def boom(q, cfg):
            raise DeepSearchError("HTTP 401")

        monkeypatch.setitem(dss.PROVIDER_HANDLERS, "tavily", boom)
        with pytest.raises(DeepSearchError, match="HTTP 401"):
            deep_search("python", config=_config())
