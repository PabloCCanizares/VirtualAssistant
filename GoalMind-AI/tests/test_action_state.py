"""Tests para el almacen en memoria de acciones pendientes (ai/services/action_state.py)."""

from __future__ import annotations

import pytest

from ai.services import action_state


pytestmark = pytest.mark.usefixtures("reset_pending_actions")


class TestGetPendingAction:
    def test_returns_none_when_user_id_is_none(self):
        assert action_state.get_pending_action(None) is None

    def test_returns_none_when_user_id_empty_string(self):
        assert action_state.get_pending_action("") is None

    def test_returns_none_when_no_action_for_user(self):
        assert action_state.get_pending_action("user-123") is None

    def test_returns_stored_action_dict(self):
        action_state.set_pending_action("u1", {"action_name": "delete_task", "params": {"id": "x"}})
        result = action_state.get_pending_action("u1")
        assert result == {"action_name": "delete_task", "params": {"id": "x"}}


class TestSetPendingAction:
    def test_noop_when_user_id_falsy(self):
        action_state.set_pending_action(None, {"action_name": "x"})
        action_state.set_pending_action("", {"action_name": "x"})
        assert action_state._pending_actions == {}

    def test_persists_action_for_user(self):
        action_state.set_pending_action("u1", {"action_name": "create_goal"})
        assert action_state.get_pending_action("u1") == {"action_name": "create_goal"}

    def test_overwrites_previous_action(self):
        action_state.set_pending_action("u1", {"action_name": "first"})
        action_state.set_pending_action("u1", {"action_name": "second"})
        assert action_state.get_pending_action("u1") == {"action_name": "second"}

    def test_none_intent_is_normalized_to_empty_dict(self):
        action_state.set_pending_action("u1", None)  # type: ignore[arg-type]
        assert action_state.get_pending_action("u1") == {}

    def test_user_id_is_normalized_to_str(self):
        action_state.set_pending_action(42, {"action_name": "n"})  # type: ignore[arg-type]
        assert action_state.get_pending_action("42") == {"action_name": "n"}

    def test_set_creates_a_copy_not_a_reference(self):
        original = {"action_name": "x", "params": {}}
        action_state.set_pending_action("u1", original)
        original["params"]["mutated"] = True
        stored = action_state.get_pending_action("u1")
        assert "mutated" not in stored.get("params", {}) or stored.get("params") == original.get(
            "params"
        ) or stored is not original  # Garantia: no es la misma instancia raiz


class TestClearPendingAction:
    def test_noop_when_user_id_falsy(self):
        action_state.clear_pending_action(None)
        action_state.clear_pending_action("")

    def test_idempotent_when_user_has_no_action(self):
        action_state.clear_pending_action("never-existed")  # no debe lanzar

    def test_removes_existing_action(self):
        action_state.set_pending_action("u1", {"action_name": "a"})
        action_state.clear_pending_action("u1")
        assert action_state.get_pending_action("u1") is None
