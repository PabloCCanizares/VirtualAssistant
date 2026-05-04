"""Tests para ai.agents.action_planner: parser JSON tolerante, validacion y confirmaciones."""

from __future__ import annotations

from ai.agents import action_planner as ap


class TestSafeParseJson:
    def test_empty_text_returns_empty_dict(self):
        assert ap._safe_parse_json("") == {}
        assert ap._safe_parse_json(None) == {}  # type: ignore[arg-type]

    def test_valid_json_parsed(self):
        assert ap._safe_parse_json('{"a": 1}') == {"a": 1}

    def test_extracts_json_from_surrounding_text(self):
        raw = "Aqui tienes el plan:\n{\"actions\": []}\nFin."
        assert ap._safe_parse_json(raw) == {"actions": []}

    def test_returns_empty_when_no_json(self):
        assert ap._safe_parse_json("texto sin json") == {}

    def test_returns_empty_when_malformed_json(self):
        assert ap._safe_parse_json("{ not json } trailing") == {}

    def test_handles_nested_json(self):
        raw = 'pre {"k": {"x": [1,2]}} post'
        assert ap._safe_parse_json(raw) == {"k": {"x": [1, 2]}}


class TestValidateAction:
    def test_rejects_non_dict(self):
        assert ap._validate_action("create_task") is None
        assert ap._validate_action(None) is None
        assert ap._validate_action(["create_task"]) is None

    def test_rejects_unknown_action_name(self):
        assert ap._validate_action({"action_name": "do_evil"}) is None

    def test_rejects_missing_action_name(self):
        assert ap._validate_action({"action_parameters": {}}) is None

    def test_rejects_non_string_action_name(self):
        assert ap._validate_action({"action_name": 42}) is None

    def test_normalizes_valid_action(self):
        out = ap._validate_action({"action_name": "  create_task  ", "action_parameters": {"titulo": "X"}})
        assert out == {
            "action_name": "create_task",
            "action_parameters": {"titulo": "X"},
            "ref_id": None,
        }

    def test_invalid_params_become_empty_dict(self):
        out = ap._validate_action({"action_name": "create_task", "action_parameters": "bad"})
        assert out["action_parameters"] == {}

    def test_ref_id_kept_when_valid_string(self):
        out = ap._validate_action({"action_name": "create_task", "ref_id": "tmp-1"})
        assert out["ref_id"] == "tmp-1"

    def test_ref_id_dropped_when_blank(self):
        out = ap._validate_action({"action_name": "create_task", "ref_id": "   "})
        assert out["ref_id"] is None


class TestNeedsConfirmation:
    def test_empty_list_returns_false(self):
        assert ap._needs_confirmation([]) is False

    def test_only_safe_actions_returns_false(self):
        actions = [
            {"action_name": "create_task"},
            {"action_name": "create_goal"},
            {"action_name": "update_project"},
        ]
        assert ap._needs_confirmation(actions) is False

    def test_destructive_action_triggers_confirmation(self):
        actions = [{"action_name": "create_task"}, {"action_name": "delete_goal"}]
        assert ap._needs_confirmation(actions) is True

    def test_each_destructive_action_triggers(self):
        for destructive in ("delete_project", "delete_goal", "delete_task", "delete_event"):
            assert ap._needs_confirmation([{"action_name": destructive}]) is True


class TestAllowedActions:
    def test_allowed_actions_set_is_complete(self):
        # Aseguramos que el conjunto cubra las operaciones CRUD esperadas.
        expected = {
            "create_project", "create_goal", "create_task",
            "update_project", "update_goal", "update_task",
            "delete_project", "delete_goal", "delete_task", "delete_event",
            "mark_task_complete", "create_event",
        }
        assert ap.ALLOWED_ACTIONS == expected

    def test_confirm_required_subset_of_allowed(self):
        assert ap.CONFIRM_REQUIRED_ACTIONS.issubset(ap.ALLOWED_ACTIONS)
