"""Tests para deep_research/planner: parser de plan, fallback heuristico y normalizado."""

from __future__ import annotations

from ai.deep_research import planner


class TestExtractJsonPayload:
    def test_empty_returns_empty_dict(self):
        assert planner._extract_json_payload("") == {}

    def test_strict_dict_parsed(self):
        assert planner._extract_json_payload('{"k": 1}') == {"k": 1}

    def test_non_dict_payload_rejected(self):
        # Si la cadena entera es JSON valido pero no un dict, debe devolver {}
        assert planner._extract_json_payload("[1,2,3]") == {}

    def test_recovery_from_surrounding_text(self):
        raw = 'Razonamiento... {"tasks": []} fin'
        assert planner._extract_json_payload(raw) == {"tasks": []}

    def test_unparseable_returns_empty(self):
        assert planner._extract_json_payload("nada") == {}


class TestCleanTitle:
    def test_collapses_whitespace(self):
        assert planner._clean_title("  hola   mundo  ", fallback="x") == "hola mundo"

    def test_caps_at_120_chars(self):
        long = "a" * 200
        assert len(planner._clean_title(long, fallback="x")) == 120

    def test_uses_fallback_when_empty(self):
        assert planner._clean_title("", fallback="default") == "default"
        assert planner._clean_title("   ", fallback="default") == "default"


class TestFallbackTasks:
    def test_returns_blueprint_capped_at_max(self):
        tasks = planner._fallback_tasks("¿que comer?", max_tasks=2)
        assert len(tasks) == 2
        assert tasks[0].task_id == "task-1"
        assert "¿que comer?" in tasks[0].objective

    def test_floor_of_one_task_when_max_is_zero(self):
        tasks = planner._fallback_tasks("query", max_tasks=0)
        assert len(tasks) == 1

    def test_three_tasks_when_max_three(self):
        tasks = planner._fallback_tasks("query", max_tasks=5)
        assert len(tasks) == 3  # blueprint solo tiene 3 entradas
        # priorities estrictamente crecientes (10, 30, 50)
        priorities = [t.priority for t in tasks]
        assert priorities == sorted(priorities)


class TestNormalizeTasks:
    def test_skips_non_dict_entries(self):
        out = planner._normalize_tasks(["bad", 42, None], max_tasks=3, fallback_query="q")
        assert out == []

    def test_keeps_max_tasks_only(self):
        raw = [{"task_id": str(i), "title": f"t{i}", "objective": "o"} for i in range(10)]
        out = planner._normalize_tasks(raw, max_tasks=3, fallback_query="q")
        assert len(out) == 3

    def test_fills_missing_fields(self):
        out = planner._normalize_tasks(
            [{}], max_tasks=1, fallback_query="mi consulta"
        )
        assert len(out) == 1
        t = out[0]
        assert t.task_id.startswith("task-")
        assert t.title == "Tarea 1"
        assert "mi consulta" in t.objective
        assert t.priority == 50  # default

    def test_clamps_priority_within_bounds(self):
        out = planner._normalize_tasks(
            [
                {"title": "alta", "priority": 0},
                {"title": "extra", "priority": 999},
                {"title": "ok", "priority": 42},
            ],
            max_tasks=3,
            fallback_query="q",
        )
        assert out[0].priority == 1
        assert out[1].priority == 100
        assert out[2].priority == 42

    def test_non_int_priority_falls_back_to_fifty(self):
        out = planner._normalize_tasks(
            [{"title": "x", "priority": "alta"}], max_tasks=1, fallback_query="q"
        )
        assert out[0].priority == 50

    def test_truncates_long_task_id(self):
        raw = [{"task_id": "x" * 500, "title": "t", "objective": "o"}]
        out = planner._normalize_tasks(raw, max_tasks=1, fallback_query="q")
        assert len(out[0].task_id) <= 40
