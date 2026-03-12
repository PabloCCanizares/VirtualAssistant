import pytest

from ai.config import DeepSearchConfig
from ai.services.deep_search_service import DeepSearchError, deep_search


def _enabled_config(**overrides):
    base = dict(
        enabled=True,
        provider="tavily",
        api_key="test-key",
        max_results=5,
        timeout_seconds=10,
        max_sources=3,
        mode_default="auto",
    )
    base.update(overrides)
    return DeepSearchConfig(**base)


def test_deep_search_disabled_raises():
    config = _enabled_config(enabled=False)
    with pytest.raises(DeepSearchError, match="deshabilitado"):
        deep_search("consulta", config=config)


def test_deep_search_missing_api_key_raises():
    config = _enabled_config(api_key="")
    with pytest.raises(DeepSearchError, match="DEEP_SEARCH_API_KEY"):
        deep_search("consulta", config=config)


def test_deep_search_tavily_normalizes_and_dedupes(monkeypatch):
    config = _enabled_config(provider="tavily", max_results=2)

    def _fake_post_json(_url, _payload, *, headers, timeout_seconds):
        assert headers["Content-Type"] == "application/json"
        assert timeout_seconds == 10
        return {
            "results": [
                {
                    "title": "A",
                    "url": "https://example.com/a",
                    "content": "uno",
                    "score": 0.2,
                },
                {
                    "title": "A mejor",
                    "url": "https://example.com/a",
                    "content": "uno mejor",
                    "score": 0.9,
                },
                {
                    "title": "B",
                    "url": "https://example.com/b",
                    "content": "dos",
                    "score": 0.3,
                },
            ]
        }

    monkeypatch.setattr("ai.services.deep_search_service._http_post_json", _fake_post_json)

    results = deep_search("consulta", config=config)

    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["title"] == "A mejor"
    assert results[1]["url"] == "https://example.com/b"


def test_deep_search_returns_empty_when_query_is_blank():
    config = _enabled_config()
    assert deep_search("   ", config=config) == []
