"""Tests para las funciones de enrutamiento del grafo (ai.graph)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from ai import graph


class TestHistoryToMessages:
    def test_empty_history_returns_empty_list(self):
        assert graph._history_to_messages(None) == []
        assert graph._history_to_messages([]) == []

    def test_skips_non_dict_items(self):
        out = graph._history_to_messages([{"role": "user", "content": "hi"}, "noise", 42])
        assert len(out) == 1

    def test_skips_empty_content(self):
        out = graph._history_to_messages([{"role": "user", "content": "   "}])
        assert out == []

    def test_maps_user_to_human_message(self):
        out = graph._history_to_messages([{"role": "user", "content": "hola"}])
        assert isinstance(out[0], HumanMessage)
        assert out[0].content == "hola"

    def test_maps_assistant_to_ai_message(self):
        out = graph._history_to_messages([{"role": "assistant", "content": "buenas"}])
        assert isinstance(out[0], AIMessage)

    def test_unknown_roles_are_skipped(self):
        out = graph._history_to_messages([{"role": "system", "content": "x"}])
        assert out == []


class TestRouteAfterSupervisor:
    def test_maps_known_categories(self):
        for category, expected_node in [
            ("action", "action_planner"),
            ("weekly_summary", "weekly_summary"),
            ("weekly_plan", "weekly_planner"),
            ("recommendations", "recommendations"),
            ("progress", "progress_tracker"),
            ("deep_research", "deep_research"),
            ("research", "research"),
            ("document", "doc_organizer"),
            ("finalize", "finalize"),
        ]:
            state = {"route": category}
            assert graph._route_after_supervisor(state) == expected_node

    def test_unknown_category_falls_back_to_research(self):
        assert graph._route_after_supervisor({"route": "qux"}) == "research"

    def test_no_route_falls_back_to_research(self):
        assert graph._route_after_supervisor({}) == "research"


class TestRouteAfterActionPlanner:
    def test_with_queue_routes_to_queue_executor(self):
        assert graph._route_after_action_planner({"action_queue": [{"action_name": "x"}]}) == "queue_executor"

    def test_without_queue_routes_to_finalize(self):
        assert graph._route_after_action_planner({}) == "finalize"
        assert graph._route_after_action_planner({"action_queue": None}) == "finalize"

    def test_empty_queue_still_routes_to_queue_executor(self):
        # Diseño: action_queue=[] indica queue inicializada (modo cola activo).
        assert graph._route_after_action_planner({"action_queue": []}) == "queue_executor"


class TestRouteAfterQueueExecutor:
    def test_action_set_routes_to_executor(self):
        assert graph._route_after_queue_executor({"action_name": "create_task"}) == "action_executor"

    def test_no_action_finalizes(self):
        assert graph._route_after_queue_executor({}) == "finalize"
        assert graph._route_after_queue_executor({"action_name": None}) == "finalize"
        assert graph._route_after_queue_executor({"action_name": ""}) == "finalize"


class TestRouteAfterActionExecutor:
    def test_in_queue_mode_returns_to_queue_executor(self):
        assert graph._route_after_action_executor({"action_queue": [{"x": 1}]}) == "queue_executor"

    def test_simple_mode_finalizes(self):
        assert graph._route_after_action_executor({"action_queue": None}) == "finalize"
        assert graph._route_after_action_executor({}) == "finalize"


class TestRouteAfterWriter:
    def test_use_critic_true_goes_to_critic(self):
        assert graph._route_after_writer({"use_critic": True}) == "critic"

    def test_use_critic_false_finalizes(self):
        assert graph._route_after_writer({"use_critic": False}) == "finalize"

    def test_missing_use_critic_finalizes(self):
        assert graph._route_after_writer({}) == "finalize"


class TestRouteAfterDocOrganizer:
    def test_doc_error_goes_to_finalize(self):
        assert graph._route_after_doc_organizer({"doc_error": "x", "doc_op": "read"}) == "finalize"

    def test_write_op_routes_to_doc_writer(self):
        assert graph._route_after_doc_organizer({"doc_op": "write"}) == "doc_writer"

    def test_write_note_routes_to_doc_writer(self):
        assert graph._route_after_doc_organizer({"doc_op": "write_note"}) == "doc_writer"

    def test_other_ops_route_to_doc_reader(self):
        assert graph._route_after_doc_organizer({"doc_op": "read"}) == "doc_reader"
        assert graph._route_after_doc_organizer({}) == "doc_reader"


class TestRouteAfterDeepResearch:
    def test_error_falls_back_to_research(self):
        assert graph._route_after_deep_research({"deep_search_error": "boom"}) == "research"

    def test_with_deep_notes_goes_to_writer(self):
        assert graph._route_after_deep_research({"deep_research_notes": "lots of notes"}) == "writer"

    def test_with_research_notes_goes_to_writer(self):
        assert graph._route_after_deep_research({"research_notes": "stuff"}) == "writer"

    def test_no_notes_falls_back_to_research(self):
        assert graph._route_after_deep_research({"deep_research_notes": "   "}) == "research"
        assert graph._route_after_deep_research({}) == "research"


class TestFinalizeNode:
    def test_uses_final_response_when_available(self):
        out = graph._finalize_node({"final_response": "  Hola  "})
        assert out == {"final_response": "Hola"}

    def test_uses_draft_when_no_final(self):
        out = graph._finalize_node({"draft_response": "borrador"})
        assert out == {"final_response": "borrador"}

    def test_default_message_when_both_missing(self):
        out = graph._finalize_node({})
        assert "No pude generar" in out["final_response"]

    def test_logs_warning_when_deep_search_fails(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="ai.graph"):
            graph._finalize_node(
                {
                    "draft_response": "ok",
                    "deep_search_error": "tavily fallo",
                    "deep_search_mode": "on",
                }
            )
        assert any("Deep search no disponible" in r.message for r in caplog.records)
