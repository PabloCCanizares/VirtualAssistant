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


def test_main_graph_smoke_flow():
    llm = _SequenceLLM(
        [
            '{"action_name": null, "confidence": 0, "parameters": {}, "needs_confirmation": false, "clarification_question": null}',
            "notas de investigacion",
            "respuesta final",
        ]
    )
    app = build_chat_graph(llm)

    result = app.invoke(
        {
            "messages": [HumanMessage(content="Necesito ayuda con mis tareas")],
            "context_json": "{}",
            "user_id": "u1",
        }
    )

    assert result["final_response"] == "respuesta final"
    assert llm.calls >= 3
