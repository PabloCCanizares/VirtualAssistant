"""Tests para DeepResearchMemory: gestion de tareas, evidencia y deteccion de estancamiento."""

from __future__ import annotations

from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.types import ResearchEvidence, ResearchIteration, ResearchTask


def _evidence(**overrides):
    base = dict(
        evidence_id="e1",
        task_id="t1",
        query="q",
        title="t",
        url="https://x",
        snippet="s",
        source_type="web",
        provider="tavily",
        score=0.5,
        quality=0.5,
    )
    base.update(overrides)
    return ResearchEvidence(**base)


def _task(task_id="t1", **overrides):
    base = dict(task_id=task_id, title="t", objective="o", priority=50)
    base.update(overrides)
    return ResearchTask(**base)


class TestAddTasks:
    def test_appends_new_tasks(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks([_task("t1"), _task("t2")])
        assert [t.task_id for t in m.tasks] == ["t1", "t2"]

    def test_dedupe_by_task_id(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks([_task("t1")])
        m.add_tasks([_task("t1", title="repetida")])
        assert len(m.tasks) == 1
        assert m.tasks[0].title == "t"  # mantiene la original


class TestGetNextTask:
    def test_returns_none_when_no_tasks(self):
        m = DeepResearchMemory(user_query="q")
        assert m.get_next_task() is None

    def test_returns_none_when_all_completed(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks([_task("t1", status="completed"), _task("t2", status="failed")])
        assert m.get_next_task() is None

    def test_prefers_lower_priority_value_first(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks([_task("t1", priority=80), _task("t2", priority=10)])
        nxt = m.get_next_task()
        assert nxt.task_id == "t2"

    def test_pending_preferred_over_in_progress_at_same_priority(self):
        # status="in_progress" produce True (1) en la clave, asi que pending va primero
        m = DeepResearchMemory(user_query="q")
        m.add_tasks(
            [_task("t1", status="in_progress", priority=10), _task("t2", status="pending", priority=10)]
        )
        assert m.get_next_task().task_id == "t2"


class TestRegisterQuery:
    def test_increments_per_task_query_pair(self):
        m = DeepResearchMemory(user_query="q")
        assert m.register_query("t1", "Algo") == 1
        assert m.register_query("t1", "algo") == 2  # case-insensitive
        assert m.register_query("t1", "algo  ") == 3  # whitespace-insensitive

    def test_isolated_per_task(self):
        m = DeepResearchMemory(user_query="q")
        m.register_query("t1", "x")
        assert m.register_query("t2", "x") == 1


class TestAddEvidence:
    def test_dedupe_by_url(self):
        m = DeepResearchMemory(user_query="q")
        added = m.add_evidence([_evidence(url="https://A"), _evidence(evidence_id="e2", url="https://a")])
        assert len(added) == 1  # case-insensitive dedup
        assert len(m.evidence) == 1

    def test_internal_fingerprint_when_no_url(self):
        m = DeepResearchMemory(user_query="q")
        a = _evidence(evidence_id="e1", url="", title="A", snippet="x", source_type="internal")
        b = _evidence(evidence_id="e2", url="", title="A", snippet="x", source_type="internal")
        c = _evidence(evidence_id="e3", url="", title="B", snippet="y", source_type="internal")
        added = m.add_evidence([a, b, c])
        assert len(added) == 2  # b es duplicado de a

    def test_returns_only_added_items(self):
        m = DeepResearchMemory(user_query="q")
        m.add_evidence([_evidence(url="https://x")])
        again = m.add_evidence([_evidence(url="https://x"), _evidence(evidence_id="e2", url="https://y")])
        assert len(again) == 1
        assert again[0].url == "https://y"


class TestStagnationDetection:
    def _add_iter(self, m, quality, idx=1, task_id="t1"):
        m.add_iteration(ResearchIteration(iteration=idx, task_id=task_id, query="q", evidence_ids=[], average_quality=quality, decision="continue"))

    def test_returns_false_for_zero_limit(self):
        m = DeepResearchMemory(user_query="q")
        assert m.has_stagnated(limit=0) is False

    def test_returns_false_with_insufficient_history(self):
        m = DeepResearchMemory(user_query="q")
        self._add_iter(m, 0.4)
        assert m.has_stagnated(limit=2) is False

    def test_returns_true_when_no_meaningful_gain(self):
        m = DeepResearchMemory(user_query="q")
        self._add_iter(m, 0.50, idx=1)
        self._add_iter(m, 0.51, idx=2)
        self._add_iter(m, 0.51, idx=3)
        # ventana = [0.50, 0.51, 0.51] → max_gain=0.01 < 0.03 → estancado
        assert m.has_stagnated(limit=2) is True

    def test_returns_false_when_quality_improves(self):
        m = DeepResearchMemory(user_query="q")
        self._add_iter(m, 0.50, idx=1)
        self._add_iter(m, 0.55, idx=2)
        self._add_iter(m, 0.60, idx=3)
        # ganancia 0.10 > 0.03 → no estancado
        assert m.has_stagnated(limit=2) is False


class TestCompletionRatios:
    def test_all_tasks_completed_false_when_empty(self):
        m = DeepResearchMemory(user_query="q")
        assert m.all_tasks_completed() is False

    def test_all_tasks_completed_true_when_all_done(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks([_task("a", status="completed"), _task("b", status="failed")])
        assert m.all_tasks_completed() is True

    def test_completion_ratio_zero_when_empty(self):
        m = DeepResearchMemory(user_query="q")
        assert m.task_completion_ratio() == 0.0

    def test_completion_ratio(self):
        m = DeepResearchMemory(user_query="q")
        m.add_tasks(
            [
                _task("a", status="completed"),
                _task("b", status="completed"),
                _task("c", status="failed"),
                _task("d", status="pending"),
            ]
        )
        assert m.task_completion_ratio() == 0.5


class TestTopSources:
    def test_sorted_by_quality_desc_and_limited(self):
        m = DeepResearchMemory(user_query="q")
        m.evidence = [
            _evidence(evidence_id=f"e{i}", url=f"https://x/{i}", quality=q)
            for i, q in enumerate([0.2, 0.9, 0.5])
        ]
        top = m.top_sources(limit=2)
        assert len(top) == 2
        assert top[0]["quality"] >= top[1]["quality"]

    def test_returns_empty_when_limit_negative_or_zero(self):
        m = DeepResearchMemory(user_query="q")
        m.evidence = [_evidence(quality=0.9)]
        assert m.top_sources(limit=0) == []
        assert m.top_sources(limit=-3) == []
