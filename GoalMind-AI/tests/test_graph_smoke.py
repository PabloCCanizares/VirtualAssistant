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


def test_main_graph_smoke_research_flow():
    """Supervisor clasifica como 'research' → research → writer → finalize."""
    llm = _SequenceLLM(
        [
            # 1) supervisor: clasifica como research
            '{"category": "research", "use_critic": false}',
            # 2) research: notas
            "notas de investigacion",
            # 3) writer: respuesta final
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


def test_main_graph_smoke_action_flow():
    """Supervisor clasifica como 'action' → intent_interpreter → action_executor → finalize."""
    llm = _SequenceLLM(
        [
            # 1) supervisor: clasifica como action
            '{"category": "action", "use_critic": false}',
            # 2) intent_interpreter: accion clara pero sin titulo → clarificacion
            '{"action_name": "create_project", "confidence": 0.9, "parameters": {}, '
            '"needs_confirmation": false, "clarification_question": "Cual es el titulo del proyecto?"}',
        ]
    )
    app = build_chat_graph(llm)

    result = app.invoke(
        {
            "messages": [HumanMessage(content="Crea un proyecto")],
            "context_json": "{}",
            "user_id": "u1",
        }
    )

    assert "titulo del proyecto" in result["final_response"].lower()


def test_main_graph_smoke_weekly_summary_flow():
    """Supervisor clasifica como 'weekly_summary' → weekly_summary → finalize."""
    llm = _SequenceLLM(
        [
            # 1) supervisor: clasifica como weekly_summary
            '{"category": "weekly_summary", "use_critic": false}',
            # 2) weekly_summary: genera resumen
            "Resumen de tu semana: has avanzado en 3 tareas.",
        ]
    )
    app = build_chat_graph(llm)

    result = app.invoke(
        {
            "messages": [HumanMessage(content="Hazme un resumen de la semana")],
            "context_json": "{}",
            "user_id": "u1",
        }
    )

    assert "resumen" in result["final_response"].lower()


def test_main_graph_smoke_progress_flow():
    """Supervisor clasifica como 'progress' → progress_tracker → writer → finalize."""
    llm = _SequenceLLM(
        [
            # 1) supervisor: clasifica como progress
            '{"category": "progress", "use_critic": false}',
            # 2) progress_tracker: analisis
            "Progreso global: 45%. Proyecto TFG al 60%.",
            # 3) writer: narra el progreso
            "Vas bien con tus objetivos. Tu proyecto TFG lleva un 60% de avance.",
        ]
    )
    app = build_chat_graph(llm)

    result = app.invoke(
        {
            "messages": [HumanMessage(content="Como voy con mis objetivos?")],
            "context_json": "{}",
            "user_id": "u1",
        }
    )

    assert result["final_response"]
    assert llm.calls >= 3


def test_main_graph_smoke_off_topic_flow():
    """Supervisor clasifica como 'off_topic' → finalize (mensaje fijo)."""
    llm = _SequenceLLM(
        [
            # 1) supervisor: clasifica como off_topic
            '{"category": "off_topic", "use_critic": false}',
        ]
    )
    app = build_chat_graph(llm)

    result = app.invoke(
        {
            "messages": [HumanMessage(content="¿Cual es la capital de Francia?")],
            "context_json": "{}",
            "user_id": "u1",
        }
    )

    # Se inyecta el mensaje fijo directamente desde supervisor
    assert "solo puedo ayudarte" in result["final_response"].lower()
    assert "proyectos" in result["final_response"].lower()
    # Solo se llamó una vez (supervisor, sin más LLM calls)
    assert llm.calls == 1
