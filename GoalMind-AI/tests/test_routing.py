import pytest
from langchain_core.messages import HumanMessage

pytest.importorskip("langgraph")

from ai.agents.supervisor import route_after_supervisor, supervisor_node
from ai.graph import (
    _history_to_messages,
    _route_after_action_executor,
    _route_after_action_planner,
    _route_after_deep_research,
    _route_after_queue_executor,
    _route_after_writer,
)


def test_history_to_messages_filters_invalid_entries():
    history = [
        {"role": "user", "content": " hola "},
        {"role": "assistant", "content": " ok "},
        {"role": "user", "content": "   "},
        {"role": "system", "content": "ignorar"},
        "no-dict",
    ]
    messages = _history_to_messages(history)

    assert len(messages) == 2
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "hola"


def test_route_after_writer_respects_use_critic():
    assert _route_after_writer({"use_critic": True}) == "critic"
    assert _route_after_writer({"use_critic": False}) == "finalize"


def test_route_after_action_planner_goes_to_queue_when_queue_exists():
    next_node = _route_after_action_planner({"action_queue": [{"action_name": "create_project"}]})
    assert next_node == "queue_executor"


def test_route_after_action_planner_goes_finalize_without_queue():
    next_node = _route_after_action_planner({})
    assert next_node == "finalize"


def test_route_after_queue_executor_to_action_executor_when_action_name_exists():
    next_node = _route_after_queue_executor({"action_name": "create_project"})
    assert next_node == "action_executor"


def test_route_after_queue_executor_to_finalize_when_action_name_missing():
    next_node = _route_after_queue_executor({})
    assert next_node == "finalize"


def test_route_after_action_executor_returns_queue_executor_in_queue_mode():
    next_node = _route_after_action_executor({"action_queue": []})
    assert next_node == "queue_executor"


def test_route_after_action_executor_returns_finalize_without_queue():
    next_node = _route_after_action_executor({})
    assert next_node == "finalize"


def test_route_after_deep_research_fallbacks_to_research_on_error():
    next_node = _route_after_deep_research({"deep_search_error": "fallo proveedor"})
    assert next_node == "research"


def test_route_after_deep_research_goes_writer_with_notes():
    next_node = _route_after_deep_research({"deep_research_notes": "notas válidas"})
    assert next_node == "writer"


def test_supervisor_routes_pending_confirmation_to_action_executor():
    state = {
        "messages": [HumanMessage(content="confirmo")],
        "pending_action_intent": {"action_name": "delete_project", "parameters": {"project_id": "p1"}},
    }
    result = supervisor_node(state, None)

    assert route_after_supervisor(result) == "action_executor"
    assert result["action_confirmed"] is True


def test_supervisor_keeps_pending_when_message_is_ambiguous():
    state = {
        "messages": [HumanMessage(content="y tambien otra cosa")],
        "pending_action_intent": {"action_name": "delete_goal", "parameters": {"goal_id": "g1"}},
    }
    result = supervisor_node(state, None)

    assert route_after_supervisor(result) == "finalize"
    assert "accion pendiente" in result["final_response"].lower()


def test_supervisor_off_topic_injects_message():
    """Cuando el LLM detecta off_topic, se inyecta mensaje fijo y se enruta a finalize."""
    class _MockLLM:
        def invoke(self, messages):
            class Response:
                content = '{"category": "off_topic", "use_critic": false}'
            return Response()
    
    state = {
        "messages": [HumanMessage(content="¿Cual es la capital de Francia?")],
        "user_id": "u1",
    }
    result = supervisor_node(state, _MockLLM())

    assert result["query_type"] == "off_topic"
    assert route_after_supervisor(result) == "finalize"
    assert "solo puedo ayudarte" in result["final_response"].lower()


def test_supervisor_off_topic_example_chiste():
    """Otro ejemplo: chiste → off_topic."""
    class _MockLLM:
        def invoke(self, messages):
            class Response:
                content = '{"category": "off_topic", "use_critic": false}'
            return Response()
    
    state = {
        "messages": [HumanMessage(content="Cuéntame un chiste")],
        "user_id": "u1",
    }
    result = supervisor_node(state, _MockLLM())

    assert result["query_type"] == "off_topic"
    assert "gestion de tus proyectos" in result["final_response"]


def test_supervisor_promotes_research_to_deep_research_when_requested():
    class _MockLLM:
        def invoke(self, messages):
            class Response:
                content = '{"category": "research", "use_critic": false}'
            return Response()

    state = {
        "messages": [HumanMessage(content="Investiga sobre este tema")],
        "deep_search_requested": True,
        "user_id": "u1",
    }
    result = supervisor_node(state, _MockLLM())

    assert result["query_type"] == "deep_research"
    assert route_after_supervisor(result) == "deep_research"
