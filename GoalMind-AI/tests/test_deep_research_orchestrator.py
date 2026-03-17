from ai.config import DeepSearchConfig
from ai.deep_research.orchestrator import run_deep_research
from ai.deep_research.types import DeepResearchRuntimeConfig
from ai.services.deep_search_service import DeepSearchError


class _Response:
    def __init__(self, content: str):
        self.content = content


class _SequenceLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def invoke(self, _messages):
        idx = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return _Response(self.outputs[idx])


def _search_cfg() -> DeepSearchConfig:
    return DeepSearchConfig(
        enabled=True,
        provider="tavily",
        api_key="key",
        max_results=5,
        timeout_seconds=10,
        max_sources=4,
        mode_default="auto",
    )


def test_orchestrator_runs_full_cycle_with_plan_loop_and_report():
    llm = _SequenceLLM(
        [
            "planner sin json",  # planner -> fallback
            '{"queries": ["tecnica pomodoro evidencia cientifica"]}',  # query generation
            "Informe final estructurado",  # report generation
        ]
    )
    runtime = DeepResearchRuntimeConfig(
        max_iterations=1,
        max_tasks=1,
        max_queries_per_task=2,
        quality_threshold=0.2,
        stagnation_limit=2,
        loop_repeat_limit=2,
        max_report_sources=5,
        internal_source_limit=0,
        parallel_queries=False,
    )

    def _web_search(_query, config=None):
        return [
            {
                "title": "Fuente A",
                "url": "https://example.org/a",
                "snippet": "Pomodoro mejora la gestion del tiempo en estudiantes.",
                "score": 0.8,
                "provider": "tavily",
            }
        ]

    result = run_deep_research(
        user_query="investigar pomodoro",
        context_json="{}",
        llm=llm,
        search_config=_search_cfg(),
        runtime_config=runtime,
        web_search_tool=_web_search,
    )

    assert result.error == ""
    assert "Informe final" in result.report
    assert len(result.sources) >= 1
    assert len(result.plan) == 1
    assert len(result.iterations) == 1


def test_orchestrator_returns_error_when_no_evidence_available():
    llm = _SequenceLLM(
        [
            "planner sin json",
            '{"queries": ["consulta sin resultados"]}',
        ]
    )
    runtime = DeepResearchRuntimeConfig(
        max_iterations=1,
        max_tasks=1,
        max_queries_per_task=1,
        quality_threshold=0.6,
        stagnation_limit=1,
        loop_repeat_limit=2,
        max_report_sources=5,
        internal_source_limit=0,
        parallel_queries=False,
    )

    def _raise(_query, config=None):
        raise DeepSearchError("fallo proveedor")

    result = run_deep_research(
        user_query="consulta",
        context_json="{}",
        llm=llm,
        search_config=_search_cfg(),
        runtime_config=runtime,
        web_search_tool=_raise,
    )

    assert "fallo proveedor" in result.error
    assert result.report == ""
    assert result.sources == []


def test_orchestrator_detects_query_loops_and_warns():
    llm = _SequenceLLM(
        [
            "planner sin json",
            '{"queries": ["misma query"]}',
            '{"queries": ["misma query"]}',
        ]
    )
    runtime = DeepResearchRuntimeConfig(
        max_iterations=3,
        max_tasks=1,
        max_queries_per_task=2,
        quality_threshold=0.9,
        stagnation_limit=1,
        loop_repeat_limit=1,
        max_report_sources=5,
        internal_source_limit=0,
        parallel_queries=False,
    )

    result = run_deep_research(
        user_query="consulta",
        context_json="{}",
        llm=llm,
        search_config=_search_cfg(),
        runtime_config=runtime,
        web_search_tool=lambda _query, config=None: [],
    )

    assert any("Query repetida descartada" in warning for warning in result.warnings)
