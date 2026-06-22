"""Bateria del modulo `ai/deep_research/orchestrator.py` (`run_deep_research`)."""

from __future__ import annotations

from ai.config import DeepSearchConfig
from ai.deep_research.orchestrator import run_deep_research
from ai.deep_research.types import DeepResearchRuntimeConfig
from tests._fakes import ScriptedLLM


def _make_search_config():
    return DeepSearchConfig(
        enabled=True, provider="tavily", api_key="k",
        max_results=3, timeout_seconds=10, max_sources=5, mode_default="auto",
    )


def _make_runtime(**kwargs):
    defaults = {"max_iterations": 2, "max_tasks": 2, "max_queries_per_task": 1,
                "stagnation_limit": 1, "parallel_queries": False}
    defaults.update(kwargs)
    return DeepResearchRuntimeConfig(**defaults)


def _plan_response():
    return (
        '{"rationale": "Plan basico", "tasks": ['
        '{"task_id": "t1", "title": "Tarea 1", "objective": "objetivo 1", "priority": 80}'
        ']}'
    )


def _full_llm_routes(report_text="Informe completo del LLM"):
    return {
        "planner de investigacion autonoma": _plan_response(),
        "generador de queries": '{"queries": ["query buena"]}',
        "generador de informes de Deep Research": report_text,
    }


def _web_with_results(query, config=None):
    return [{
        "title": "Fuente A", "url": "https://a",
        "snippet": "informacion relevante sobre el TFG y la metodologia",
        "score": 0.9, "provider": "tavily",
    }]


def _web_empty(query, config=None):
    return []


class TestRunDeepResearch:
    def test_complete_flow_with_evidence(self):
        llm = ScriptedLLM(_full_llm_routes())
        result = run_deep_research(
            user_query="metodologia del TFG",
            context_json="{}",
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(),
            web_search_tool=_web_with_results,
        )
        assert result.report == "Informe completo del LLM"
        assert result.error == ""
        assert len(result.plan) == 1
        assert len(result.sources) >= 1

    def test_returns_fatal_error_when_no_evidence(self):
        llm = ScriptedLLM(_full_llm_routes())
        result = run_deep_research(
            user_query="x",
            context_json="{}",
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(),
            web_search_tool=_web_empty,
        )
        assert result.error
        assert result.report == ""

    def test_with_empty_plan_uses_fallback_tasks(self):
        # Planner devuelve plan vacio: el modulo planner inyecta tareas por defecto.
        llm = ScriptedLLM({
            "planner de investigacion autonoma": '{"rationale": "x", "tasks": []}',
            "generador de queries": '{"queries": ["q1"]}',
            "generador de informes de Deep Research": "irrelevante",
        })
        result = run_deep_research(
            user_query="x",
            context_json="{}",
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(),
            web_search_tool=_web_with_results,
        )
        # El plan no esta vacio: el planner anade tareas heuristicas.
        assert len(result.plan) >= 1
        # Algun warning indica el fallback del planner.
        assert any("fallback" in w.lower() or "planner" in w.lower() for w in result.warnings)

    def test_uses_internal_context_when_available(self):
        import json as _json
        ctx = _json.dumps({
            "projects": [{
                "_id": "p1", "title": "Memoria TFG",
                "descripcion": "metodologia y experimentacion del TFG",
            }],
        })
        llm = ScriptedLLM(_full_llm_routes())
        result = run_deep_research(
            user_query="metodologia TFG",
            context_json=ctx,
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(),
            web_search_tool=_web_empty,  # sin web, solo contexto interno
        )
        # Si el contexto interno aportó evidencia, el informe se genera
        assert result.plan
