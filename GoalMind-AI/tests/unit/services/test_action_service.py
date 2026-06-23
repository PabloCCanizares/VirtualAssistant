import json

import pytest

from services.action_service import execute_action

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _state(action_name, parameters=None, context=None, **extra):
    return {
        "user_id": USER_ID,
        "pending_action_intent": {"action_name": action_name, "parameters": parameters or {}},
        "action_confirmed": True,
        "context_json": json.dumps(context or {}),
        **extra,
    }


class TestActionService:
    def test_execute_action_creates_project_without_agent_node(self, mongo_mock):
        out = execute_action(_state("create_project", {"titulo": "Agent OS"}))

        assert "Proyecto creado" in out["final_response"]
        assert mongo_mock.local_db["Projects"].count_documents({"titulo": "Agent OS"}) == 1

    def test_execute_action_keeps_confirmation_gate(self):
        state = _state("delete_task", {"task_id": "x"}, action_confirmed=False)

        out = execute_action(state)

        assert "confirmacion" in out["final_response"]
        assert out["pending_action_intent"]["action_name"] == "delete_task"
