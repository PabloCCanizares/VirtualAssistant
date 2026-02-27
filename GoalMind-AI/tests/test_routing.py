import pytest
from langchain_core.messages import HumanMessage

pytest.importorskip("langgraph")

from ai.agents.supervisor import route_after_supervisor, supervisor_node
from ai.graph import _history_to_messages, _route_after_intent, _route_after_writer


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


def test_route_after_intent_uses_finalize_when_clarification_exists():
    next_node = _route_after_intent({"action_clarification_question": "Que proyecto?"})
    assert next_node == "finalize"


def test_route_after_intent_finalize_when_low_confidence():
    """Con baja confianza, el nuevo routing va a finalize (ya no hay fallback)."""
    next_node = _route_after_intent(
        {
            "action_name": "create_project",
            "action_confidence": 0.25,
        }
    )
    assert next_node == "finalize"


def test_route_after_intent_action_executor_when_high_confidence():
    next_node = _route_after_intent(
        {
            "action_name": "create_project",
            "action_confidence": 0.9,
            "action_needs_confirmation": False,
        }
    )
    assert next_node == "action_executor"


def test_route_after_intent_finalize_when_needs_confirmation():
    next_node = _route_after_intent(
        {
            "action_name": "delete_project",
            "action_confidence": 0.95,
            "action_needs_confirmation": True,
        }
    )
    assert next_node == "finalize"


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
