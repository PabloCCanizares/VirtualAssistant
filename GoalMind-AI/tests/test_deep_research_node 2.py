from langchain_core.messages import HumanMessage

from ai.config import DeepSearchConfig
from ai.agents.deep_research import deep_research_node
from ai.services.deep_search_service import DeepSearchError


class _Response:
    def __init__(self, content: str):
        self.content = content


class _MockLLM:
    def __init__(self, content="sintesis"):
        self.content = content

    def invoke(self, _messages):
        return _Response(self.content)


def test_deep_research_node_returns_empty_when_not_requested():
    state = {
        "deep_search_requested": False,
        "messages": [HumanMessage(content="hola")],
    }
    result = deep_research_node(state, _MockLLM())
    assert result == {}


def test_deep_research_node_returns_error_without_query():
    state = {
        "deep_search_requested": True,
        "messages": [],
    }
    result = deep_research_node(state, _MockLLM())
    assert "consulta" in result["deep_search_error"].lower()


def test_deep_research_node_success(monkeypatch):
    cfg = DeepSearchConfig(
        enabled=True,
        provider="tavily",
        api_key="k",
        max_results=5,
        timeout_seconds=10,
        max_sources=2,
        mode_default="auto",
    )
    results = [
        {
            "title": "Fuente A",
            "url": "https://a.test",
            "snippet": "snippet-a",
            "score": 0.8,
            "provider": "tavily",
        },
        {
            "title": "Fuente B",
            "url": "https://b.test",
            "snippet": "snippet-b",
            "score": 0.6,
            "provider": "tavily",
        },
    ]
    monkeypatch.setattr("ai.agents.deep_research.get_deep_search_config", lambda: cfg)
    monkeypatch.setattr("ai.agents.deep_research.deep_search", lambda _query, config=None: results)

    state = {
        "deep_search_requested": True,
        "messages": [HumanMessage(content="Investiga este tema")],
    }
    result = deep_research_node(state, _MockLLM(content="sintesis final"))

    assert result["deep_search_error"] == ""
    assert len(result["deep_research_sources"]) == 2
    assert result["deep_research_notes"] == "sintesis final"
    assert result["research_notes"] == "sintesis final"


def test_deep_research_node_handles_deep_search_error(monkeypatch):
    cfg = DeepSearchConfig(
        enabled=True,
        provider="tavily",
        api_key="k",
        max_results=5,
        timeout_seconds=10,
        max_sources=2,
        mode_default="auto",
    )
    monkeypatch.setattr("ai.agents.deep_research.get_deep_search_config", lambda: cfg)

    def _raise(_query, config=None):
        raise DeepSearchError("fallo proveedor")

    monkeypatch.setattr("ai.agents.deep_research.deep_search", _raise)

    state = {
        "deep_search_requested": True,
        "messages": [HumanMessage(content="Investiga este tema")],
    }
    result = deep_research_node(state, _MockLLM())

    assert "fallo proveedor" in result["deep_search_error"]
    assert result["deep_research_sources"] == []
