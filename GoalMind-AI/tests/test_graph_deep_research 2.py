import pytest
from langchain_core.messages import HumanMessage

pytest.importorskip("langgraph")

from ai.graph import build_chat_graph


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _SequenceLLM:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def invoke(self, _messages):
        output = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return _Response(output)


def test_graph_routes_deep_research_to_writer_when_success(monkeypatch):
    llm = _SequenceLLM(
        [
            '{"category": "deep_research", "use_critic": false}',  # supervisor
            "respuesta final writer",  # writer
        ]
    )
    app = build_chat_graph(llm)

    monkeypatch.setattr(
        "ai.graph.deep_research_node",
        lambda state, _llm: {"deep_research_notes": "notas profundas", "research_notes": "notas profundas"},
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="investiga con fuentes")],
            "context_json": "{}",
            "user_id": "u1",
            "deep_search_requested": True,
        }
    )

    assert result["final_response"] == "respuesta final writer"


def test_graph_fallbacks_to_research_when_deep_research_errors(monkeypatch):
    llm = _SequenceLLM(
        [
            '{"category": "deep_research", "use_critic": false}',  # supervisor
            "notas de research fallback",  # research
            "respuesta final writer",  # writer
        ]
    )
    app = build_chat_graph(llm)

    monkeypatch.setattr(
        "ai.graph.deep_research_node",
        lambda state, _llm: {"deep_search_error": "fallo proveedor"},
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="investiga con fuentes")],
            "context_json": "{}",
            "user_id": "u1",
            "deep_search_requested": True,
        }
    )

    assert "Aviso: no se pudo completar la busqueda profunda." in result["final_response"]
    assert "fallo proveedor" in result["final_response"]
    assert "respuesta final writer" in result["final_response"]
