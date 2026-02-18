import pytest
from langchain_core.messages import HumanMessage

pytest.importorskip("langgraph")

from agents.supervisor import route_after_supervisor, supervisor_node
from graph import _history_to_messages, _route_after_intent, _route_after_writer


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


def test_route_after_intent_falls_back_when_low_confidence():
    next_node = _route_after_intent(
        {
            "action_name": "create_project",
            "action_confidence": 0.25,
            "fallback_route": "recommendations",
        }
    )
    assert next_node == "recommendations"


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
