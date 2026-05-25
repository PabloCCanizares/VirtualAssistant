"""Bateria del modulo `ai/deep_research/reporter.py`."""

from __future__ import annotations

import pytest

from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.reporter import _fallback_report, generate_research_report
from ai.deep_research.types import (
    DeepResearchRuntimeConfig,
    ResearchEvidence,
    ResearchTask,
)
from tests._fakes import ScriptedLLM


def _make_memory_with_tasks_and_sources():
    m = DeepResearchMemory(user_query="consulta", context_json="{}")
    m.add_tasks([
        ResearchTask(task_id="t1", title="Tarea 1", objective="objetivo 1", status="completed", attempts=2, priority=80),
        ResearchTask(task_id="t2", title="Tarea 2", objective="objetivo 2", status="failed", attempts=1, priority=50),
    ])
    m.add_evidence([
        ResearchEvidence(
            evidence_id="e1", task_id="t1", query="q",
            title="Fuente A", url="https://a", snippet="snippet A",
            source_type="web", provider="tavily", score=0.9, quality=0.9,
        ),
    ])
    m.add_warning("warning1")
    return m


class TestFallbackReport:
    def test_includes_query_and_sections(self):
        m = _make_memory_with_tasks_and_sources()
        out = _fallback_report(m, user_query="consulta", max_sources=5)
        for section in ("Resumen ejecutivo", "Plan de investigacion",
                         "Hallazgos principales", "Calidad",
                         "Conclusiones", "Fuentes"):
            assert section in out

    def test_with_no_plan_and_no_sources(self):
        m = DeepResearchMemory(user_query="x", context_json="{}")
        out = _fallback_report(m, user_query="x", max_sources=3)
        assert "No se genero un plan" in out
        assert "No se obtuvo evidencia" in out
        assert "Sin fuentes" in out

    def test_includes_warnings_when_present(self):
        m = _make_memory_with_tasks_and_sources()
        out = _fallback_report(m, user_query="x", max_sources=3)
        assert "warning1" in out

    def test_without_warnings_states_so(self):
        m = DeepResearchMemory(user_query="x", context_json="{}")
        m.add_tasks([ResearchTask(task_id="t1", title="T", objective="o")])
        m.add_evidence([
            ResearchEvidence(
                evidence_id="e1", task_id="t1", query="q",
                title="A", url="https://a", snippet="s",
                source_type="web", provider="tavily",
            )
        ])
        out = _fallback_report(m, user_query="x", max_sources=3)
        assert "No se registraron advertencias" in out


class TestGenerateResearchReport:
    def test_uses_llm_response_when_valid(self):
        llm = ScriptedLLM({"generador de informes de Deep Research": "Informe LLM"})
        m = _make_memory_with_tasks_and_sources()
        out = generate_research_report(
            user_query="x", memory=m, llm=llm,
            runtime_config=DeepResearchRuntimeConfig(),
        )
        assert out == "Informe LLM"

    def test_falls_back_when_llm_returns_empty(self):
        llm = ScriptedLLM({"generador de informes de Deep Research": "   "})
        m = _make_memory_with_tasks_and_sources()
        out = generate_research_report(
            user_query="x", memory=m, llm=llm,
            runtime_config=DeepResearchRuntimeConfig(),
        )
        # Cae al fallback que incluye las secciones estandar
        assert "Resumen ejecutivo" in out

    def test_falls_back_when_llm_raises(self):
        llm = ScriptedLLM({"generador de informes de Deep Research": RuntimeError("LLM down")})
        m = _make_memory_with_tasks_and_sources()
        out = generate_research_report(
            user_query="x", memory=m, llm=llm,
            runtime_config=DeepResearchRuntimeConfig(),
        )
        assert "Resumen ejecutivo" in out

    def test_with_contradictions_in_fallback(self):
        m = _make_memory_with_tasks_and_sources()
        m.contradictions = ["contradiccion 1", "contradiccion 2"]
        out = _fallback_report(m, user_query="x", max_sources=3)
        assert "contradicciones" in out.lower()
