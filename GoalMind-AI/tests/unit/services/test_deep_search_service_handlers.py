"""Tests para los handlers especificos de proveedores de busqueda profunda.

Cubre `_search_tavily`, `_search_serper` y `_search_brave` interceptando
`_http_post_json` y `_http_get_json` para evitar llamadas reales.
"""

from __future__ import annotations

import pytest

from ai.config import DeepSearchConfig
from ai.services import deep_search_service
from ai.services.deep_search_service import (
    DeepSearchError,
    _search_brave,
    _search_serper,
    _search_tavily,
    deep_search,
)


def _make_config(provider="tavily"):
    return DeepSearchConfig(
        enabled=True,
        provider=provider,
        api_key="fake-key",
        max_results=5,
        timeout_seconds=10,
        max_sources=5,
        mode_default="auto",
    )


class TestTavilyHandler:
    def test_normalizes_results(self, monkeypatch):
        monkeypatch.setattr(
            deep_search_service, "_http_post_json",
            lambda url, payload, headers, timeout_seconds: {
                "results": [
                    {"title": "A", "url": "https://a", "content": "snippet A", "score": 0.9},
                    {"title": "B", "url": "https://b", "content": "snippet B", "score": 0.5},
                ]
            },
        )
        out = _search_tavily("query", _make_config("tavily"))
        assert len(out) == 2
        assert out[0]["provider"] == "tavily"

    def test_empty_results(self, monkeypatch):
        monkeypatch.setattr(
            deep_search_service, "_http_post_json",
            lambda *a, **k: {"results": []},
        )
        out = _search_tavily("query", _make_config())
        assert out == []


class TestSerperHandler:
    def test_normalizes_organic(self, monkeypatch):
        monkeypatch.setattr(
            deep_search_service, "_http_post_json",
            lambda *a, **k: {
                "organic": [
                    {"title": "A", "link": "https://a", "snippet": "x", "position": 1},
                ]
            },
        )
        out = _search_serper("query", _make_config("serper"))
        assert len(out) == 1
        assert out[0]["provider"] == "serper"


class TestBraveHandler:
    def test_normalizes_web_results(self, monkeypatch):
        monkeypatch.setattr(
            deep_search_service, "_http_get_json",
            lambda *a, **k: {
                "web": {
                    "results": [
                        {"title": "A", "url": "https://a", "description": "d", "page_age": "2026-01-01"},
                    ]
                }
            },
        )
        out = _search_brave("query", _make_config("brave"))
        assert len(out) == 1
        assert out[0]["provider"] == "brave"

    def test_no_web_field(self, monkeypatch):
        monkeypatch.setattr(
            deep_search_service, "_http_get_json",
            lambda *a, **k: {},
        )
        out = _search_brave("query", _make_config("brave"))
        assert out == []


class TestDeepSearchDispatcher:
    def test_empty_query_returns_empty(self):
        assert deep_search("   ") == []

    def test_disabled_raises(self):
        cfg = DeepSearchConfig(
            enabled=False, provider="tavily", api_key="k", max_results=5,
            timeout_seconds=10, max_sources=5, mode_default="auto",
        )
        with pytest.raises(DeepSearchError, match="deshabilitado"):
            deep_search("query", config=cfg)

    def test_missing_api_key_raises(self):
        cfg = DeepSearchConfig(
            enabled=True, provider="tavily", api_key="", max_results=5,
            timeout_seconds=10, max_sources=5, mode_default="auto",
        )
        with pytest.raises(DeepSearchError, match="DEEP_SEARCH_API_KEY"):
            deep_search("query", config=cfg)

    def test_unsupported_provider_raises(self):
        cfg = DeepSearchConfig(
            enabled=True, provider="bing", api_key="k", max_results=5,
            timeout_seconds=10, max_sources=5, mode_default="auto",
        )
        with pytest.raises(DeepSearchError, match="no soportado"):
            deep_search("query", config=cfg)

    def test_dispatcher_calls_handler(self, monkeypatch):
        monkeypatch.setitem(
            deep_search_service.PROVIDER_HANDLERS,
            "tavily",
            lambda q, cfg: [{
                "title": "A", "url": "https://a", "snippet": "s",
                "score": 1.0, "provider": "tavily", "raw": {},
            }],
        )
        out = deep_search("query", config=_make_config("tavily"))
        assert len(out) == 1

    def test_handler_propagates_deep_search_error(self, monkeypatch):
        def _boom(q, cfg):
            raise DeepSearchError("ya conocido")

        monkeypatch.setitem(deep_search_service.PROVIDER_HANDLERS, "tavily", _boom)
        with pytest.raises(DeepSearchError, match="ya conocido"):
            deep_search("query", config=_make_config("tavily"))

    def test_handler_wraps_generic_exception(self, monkeypatch):
        def _boom(q, cfg):
            raise RuntimeError("network")

        monkeypatch.setitem(deep_search_service.PROVIDER_HANDLERS, "tavily", _boom)
        with pytest.raises(DeepSearchError, match="No se pudo completar"):
            deep_search("query", config=_make_config("tavily"))
