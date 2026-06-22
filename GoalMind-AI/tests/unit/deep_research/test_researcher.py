"""Bateria del modulo `ai/deep_research/researcher.py`."""

from __future__ import annotations

import json

from ai.config import DeepSearchConfig
from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.researcher import (
    _extract_json_list,
    _fallback_queries,
    _internal_documents,
    _query_overlap_score,
    _tokenize,
    _web_search_single,
    generate_task_queries,
    run_research_step,
    search_internal_context,
)
from ai.deep_research.types import (
    DeepResearchRuntimeConfig,
    ResearchTask,
)
from ai.services.deep_search_service import DeepSearchError
from tests._fakes import ScriptedLLM


def _make_task(task_id="t1", title="redactar", objective="redactar memoria del TFG"):
    return ResearchTask(task_id=task_id, title=title, objective=objective)


def _make_memory(query="metodologia"):
    return DeepResearchMemory(user_query=query, context_json="{}")


def _make_runtime(**kwargs):
    return DeepResearchRuntimeConfig(**kwargs)


def _make_search_config():
    return DeepSearchConfig(
        enabled=True, provider="tavily", api_key="k",
        max_results=5, timeout_seconds=10, max_sources=5, mode_default="auto",
    )


class TestPureHelpers:
    def test_extract_json_list_with_object(self):
        text = '{"queries": ["a", "b"]}'
        assert _extract_json_list(text) == ["a", "b"]

    def test_extract_json_list_with_array(self):
        assert _extract_json_list('["a", "b"]') == ["a", "b"]

    def test_extract_json_list_from_surrounding_text(self):
        text = "previo [\"x\", \"y\"] posterior"
        assert _extract_json_list(text) == ["x", "y"]

    def test_extract_json_list_empty(self):
        assert _extract_json_list("") == []
        assert _extract_json_list("not json") == []

    def test_extract_json_list_filters_empty_strings(self):
        text = '{"queries": ["a", "", "  "]}'
        assert _extract_json_list(text) == ["a"]

    def test_tokenize_removes_stop_words(self):
        terms = _tokenize("la metodologia de un proyecto")
        assert "metodologia" in terms
        assert "proyecto" in terms
        assert "la" not in terms
        assert "de" not in terms

    def test_tokenize_filters_short_words(self):
        terms = _tokenize("a is on it but evidence")
        # palabras de menos de 3 chars se descartan
        assert "evidence" in terms
        assert "it" not in terms

    def test_query_overlap_score_full_match(self):
        assert _query_overlap_score("metodologia tfg", "el tfg necesita una metodologia") == 1.0

    def test_query_overlap_score_no_match(self):
        assert _query_overlap_score("xyzabc", "totalmente diferente") == 0.0

    def test_query_overlap_score_empty_query(self):
        assert _query_overlap_score("", "x") == 0.0

    def test_query_overlap_score_empty_text(self):
        assert _query_overlap_score("query", "") == 0.0

    def test_fallback_queries_returns_max(self):
        task = _make_task()
        out = _fallback_queries(task, "consulta global", max_queries=3)
        assert len(out) <= 3
        assert all(q for q in out)

    def test_fallback_queries_respects_limit(self):
        task = _make_task()
        out = _fallback_queries(task, "x", max_queries=1)
        assert len(out) == 1


class TestInternalDocuments:
    def test_returns_empty_on_invalid_json(self):
        assert _internal_documents("not-json") == []

    def test_returns_empty_on_non_dict(self):
        assert _internal_documents('["a"]') == []

    def test_extracts_known_collections(self):
        ctx = json.dumps({
            "projects": [{"_id": "p1", "title": "P"}],
            "goals": [{"_id": "g1", "title": "G"}],
            "tasks": [{"_id": "t1", "name": "T"}],
            "events": [{"_id": "e1"}],
            "unknown": [{"x": 1}],
        })
        out = _internal_documents(ctx)
        assert len(out) == 4
        names = {name for name, _ in out}
        assert names == {"projects", "goals", "tasks", "events"}


class TestSearchInternalContext:
    def test_returns_empty_with_no_documents(self):
        out = search_internal_context(
            task_id="t1", query="x", context_json="{}", source_limit=5,
        )
        assert out == []

    def test_finds_relevant_match(self):
        ctx = json.dumps({
            "projects": [{
                "_id": "p1",
                "title": "Memoria TFG",
                "descripcion": "metodologia de redaccion del TFG",
            }],
        })
        out = search_internal_context(
            task_id="t1",
            query="metodologia redaccion",
            context_json=ctx,
            source_limit=5,
        )
        assert len(out) >= 1
        assert out[0].provider == "internal_context"

    def test_filters_low_overlap(self):
        ctx = json.dumps({"projects": [{"_id": "p1", "title": "X", "descripcion": "Y"}]})
        out = search_internal_context(
            task_id="t1", query="totalmente diferente", context_json=ctx, source_limit=5,
        )
        assert out == []

    def test_respects_source_limit(self):
        ctx = json.dumps({
            "projects": [
                {"_id": f"p{i}", "title": "metodologia redaccion", "descripcion": "tfg metodologia"}
                for i in range(20)
            ],
        })
        out = search_internal_context(
            task_id="t1", query="metodologia redaccion tfg",
            context_json=ctx, source_limit=3,
        )
        assert len(out) == 3


class TestGenerateTaskQueries:
    def test_uses_llm_response(self):
        llm = ScriptedLLM({"generador de queries": '{"queries": ["q1", "q2"]}'})
        task = _make_task()
        memory = _make_memory()
        runtime = _make_runtime(max_queries_per_task=5)
        out = generate_task_queries(task=task, memory=memory, llm=llm, runtime_config=runtime)
        assert "q1" in out

    def test_dedups_and_respects_limit(self):
        llm = ScriptedLLM({"generador de queries": '{"queries": ["a", "a", "b", "c"]}'})
        task = _make_task()
        out = generate_task_queries(
            task=task, memory=_make_memory(), llm=llm,
            runtime_config=_make_runtime(max_queries_per_task=2),
        )
        assert len(out) == 2

    def test_falls_back_on_llm_exception(self):
        llm = ScriptedLLM({"generador de queries": RuntimeError("LLM down")})
        task = _make_task()
        out = generate_task_queries(
            task=task, memory=_make_memory(), llm=llm,
            runtime_config=_make_runtime(max_queries_per_task=3),
        )
        # Cae al fallback determinista
        assert len(out) >= 1

    def test_falls_back_on_empty_llm_response(self):
        llm = ScriptedLLM({"generador de queries": "respuesta sin json"})
        task = _make_task()
        out = generate_task_queries(
            task=task, memory=_make_memory(), llm=llm,
            runtime_config=_make_runtime(max_queries_per_task=2),
        )
        assert len(out) >= 1


class TestWebSearchSingle:
    def test_returns_results_on_success(self):
        def _ok(query, config=None):
            return [{"title": "A", "url": "https://a"}]

        results, err = _web_search_single("q", search_config=_make_search_config(), web_search_tool=_ok)
        assert err == ""
        assert len(results) == 1

    def test_returns_error_on_deep_search_error(self):
        def _bad(query, config=None):
            raise DeepSearchError("provider down")

        results, err = _web_search_single("q", search_config=_make_search_config(), web_search_tool=_bad)
        assert results == []
        assert "provider down" in err

    def test_returns_error_on_generic_exception(self):
        def _bad(query, config=None):
            raise RuntimeError("net")

        results, err = _web_search_single("q", search_config=_make_search_config(), web_search_tool=_bad)
        assert results == []
        assert "Error de busqueda" in err


class TestRunResearchStep:
    def test_full_flow_serial(self):
        llm = ScriptedLLM({"generador de queries": '{"queries": ["query1"]}'})

        def _web(query, config=None):
            return [{"title": "A", "url": "https://a", "snippet": "s", "score": 0.5}]

        out, accepted, warnings = run_research_step(
            task=_make_task(),
            memory=_make_memory(),
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(parallel_queries=False),
            web_search_tool=_web,
        )
        assert len(out) >= 1
        assert accepted == ["query1"]

    def test_parallel_queries_path(self):
        llm = ScriptedLLM({"generador de queries": '{"queries": ["q1", "q2"]}'})

        def _web(query, config=None):
            return [{"title": query, "url": f"https://{query}", "snippet": "s", "score": 0.5}]

        out, accepted, warnings = run_research_step(
            task=_make_task(),
            memory=_make_memory(),
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(parallel_queries=True, max_queries_per_task=2),
            web_search_tool=_web,
        )
        assert len(accepted) == 2

    def test_dedup_repeated_query_warns(self):
        # Forzamos que la misma query se repita varias veces
        llm = ScriptedLLM({"generador de queries": '{"queries": ["repe"]}'})

        def _web(q, config=None):
            return []

        memory = _make_memory()
        # Repetir 3 veces la query a mano
        for _ in range(3):
            memory.register_query("t1", "repe")

        out, accepted, warnings = run_research_step(
            task=_make_task(),
            memory=memory,
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(loop_repeat_limit=2, parallel_queries=False),
            web_search_tool=_web,
        )
        # La query repetida se descarta y se anade una advertencia
        assert any("Query repetida" in w for w in warnings)

    def test_web_search_error_logged_as_warning(self):
        llm = ScriptedLLM({"generador de queries": '{"queries": ["q1"]}'})

        def _bad(q, config=None):
            raise DeepSearchError("provider down")

        out, accepted, warnings = run_research_step(
            task=_make_task(),
            memory=_make_memory(),
            llm=llm,
            search_config=_make_search_config(),
            runtime_config=_make_runtime(parallel_queries=False),
            web_search_tool=_bad,
        )
        assert any("provider down" in w for w in warnings)
