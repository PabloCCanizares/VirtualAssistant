"""Bateria del `writer_node` y `critic_node` (ramas no cubiertas por integracion)."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

from ai.agents.writer import (
    _append_missing_sources,
    _build_sources_block,
    _normalize_sources,
    writer_node,
)
from ai.agents.critic import critic_node
from ai.agents.research import research_node, _register_document_listings
from ai.agents.deep_research import deep_research_node, _last_user_message_text
from ai.agents.recommendations import recommendations_node
from ai.agents.weekly_summary import weekly_summary_node
from ai.agents.weekly_planner import weekly_planner_node
from ai.agents.progress_tracker import progress_tracker_node

from tests._fakes import ScriptedLLM


# ---------------------------------------------------------------------------
# Helpers de writer
# ---------------------------------------------------------------------------


class TestWriterHelpers:
    def test_normalize_sources_filters_invalid(self):
        out = _normalize_sources([
            {"url": "https://a", "title": "A", "snippet": "s"},
            {"title": "no url"},        # sin url, descartado
            {"url": "", "title": "x"},  # url vacia, descartado
            "no-dict",                  # no dict, descartado
        ])
        assert len(out) == 1
        assert out[0]["url"] == "https://a"

    def test_build_sources_block_empty(self):
        assert _build_sources_block([]) == ""

    def test_build_sources_block_with_items(self):
        sources = [{"title": "T1", "url": "https://a", "snippet": ""}]
        block = _build_sources_block(sources)
        assert "Fuentes:" in block
        assert "https://a" in block

    def test_append_missing_sources_when_already_present(self):
        text = "Respuesta con https://a citada"
        sources = [{"title": "A", "url": "https://a", "snippet": ""}]
        out = _append_missing_sources(text, sources)
        # La fuente ya esta en el texto, no se añade
        assert "Fuentes:" not in out

    def test_append_missing_sources_when_missing(self):
        text = "Respuesta sin citas"
        sources = [{"title": "A", "url": "https://a", "snippet": ""}]
        out = _append_missing_sources(text, sources)
        assert "Fuentes:" in out
        assert "https://a" in out


# ---------------------------------------------------------------------------
# writer_node con/sin fuentes
# ---------------------------------------------------------------------------


class TestWriterNode:
    def test_writer_without_sources(self):
        llm = ScriptedLLM({"agente writer": "Texto generado por el writer."})
        state = {
            "messages": [HumanMessage(content="hola")],
            "research_notes": "notas",
        }
        out = writer_node(state, llm)
        assert "draft_response" in out
        assert "writer" in out["draft_response"]

    def test_writer_with_sources(self):
        llm = ScriptedLLM({"agente writer": "Una respuesta corta."})
        state = {
            "messages": [HumanMessage(content="hola")],
            "research_notes": "x",
            "deep_research_sources": [
                {"url": "https://a", "title": "A", "snippet": "s"},
            ],
        }
        out = writer_node(state, llm)
        # Las fuentes se añaden al final si no estan citadas.
        assert "Fuentes:" in out["draft_response"]
        assert "https://a" in out["draft_response"]

    def test_writer_llm_exception_yields_fallback(self):
        llm = ScriptedLLM({"agente writer": RuntimeError("LLM down")})
        out = writer_node({"messages": [], "research_notes": "x"}, llm)
        assert "No pude" in out["draft_response"]


# ---------------------------------------------------------------------------
# critic, recommendations, weekly_summary, weekly_planner, progress_tracker
# (todos son agentes simples que invocan al LLM y emiten draft_response /
#  progress_analysis)
# ---------------------------------------------------------------------------


class TestSimpleAgents:
    def test_critic_passes_draft_to_llm(self):
        llm = ScriptedLLM({"Eres el critic": "Texto revisado."})
        out = critic_node(
            {"messages": [], "draft_response": "borrador inicial"},
            llm,
        )
        assert "final_response" in out

    def test_critic_with_exception(self):
        llm = ScriptedLLM({"Eres el critic": RuntimeError("x")})
        out = critic_node({"messages": [], "draft_response": "x"}, llm)
        assert "final_response" in out

    def test_recommendations(self):
        llm = ScriptedLLM({"recomendaciones personales": "Top 1: hazlo."})
        out = recommendations_node({"messages": [], "context_json": "{}"}, llm)
        assert "draft_response" in out

    def test_recommendations_uses_context_when_llm_fails(self):
        context = json.dumps({
            "tasks": [
                {
                    "contenido": "Entregar informe",
                    "estado": "pendiente",
                    "prioridad": "alta",
                    "fecha_limite": "2026-07-04T10:00:00",
                }
            ],
            "projects": [
                {"titulo": "TFG", "estado": "activo", "progreso": 5},
            ],
            "goals": [
                {"titulo": "Cerrar capitulo", "estado": "activo", "fecha_fin": "2026-07-05"},
            ],
            "events": [
                {"titulo": "Revision", "fecha_inicio": "2026-07-05T09:00:00"},
            ],
        })
        llm = ScriptedLLM({"recomendaciones personales": RuntimeError("LLM down")})

        out = recommendations_node({"messages": [], "context_json": context}, llm)

        assert "Recomendaciones personales" in out["draft_response"]
        assert "Entregar informe" in out["draft_response"]
        assert "No pude generar" not in out["draft_response"]

    def test_weekly_summary(self):
        llm = ScriptedLLM({"resumen de la semana": "Esta semana hiciste X."})
        out = weekly_summary_node({"messages": [], "context_json": "{}"}, llm)
        assert "draft_response" in out

    def test_weekly_summary_uses_metrics_when_llm_fails(self):
        context = json.dumps({
            "summary_metrics": {
                "week_range": {"start": "2026-06-29", "end": "2026-07-05"},
                "tasks": {
                    "completed_this_week": 3,
                    "completed_delta": 1,
                    "pending_due_this_week": 2,
                    "due_today": 1,
                    "overdue": 1,
                    "high_priority_pending": 1,
                },
                "projects": {"active": 2},
                "goals": {"active": 1},
                "events": {
                    "busy_hours_week": 12,
                    "productive_hours_week": 4,
                    "focus_hours_week": 2,
                },
                "daily_metrics": {
                    "avg_sleep_hours": 7.5,
                    "avg_mood_score": 4,
                },
                "risks": [
                    {"label": "Tareas vencidas", "detail": "1 tarea pendiente ya paso su fecha."},
                ],
            },
        })
        llm = ScriptedLLM({"resumen de la semana": RuntimeError("LLM down")})

        out = weekly_summary_node({"messages": [], "context_json": context}, llm)

        assert "Resumen semanal" in out["draft_response"]
        assert "completaste 3 tareas" in out["draft_response"]
        assert "Tareas vencidas" in out["draft_response"]

    def test_weekly_planner(self):
        llm = ScriptedLLM({"planificador semanal": "Plan: hacer X el lunes."})
        out = weekly_planner_node({"messages": [], "context_json": "{}"}, llm)
        assert "draft_response" in out

    def test_progress_tracker(self):
        llm = ScriptedLLM({"analista de progreso": "Avance al 50%."})
        out = progress_tracker_node({"messages": [], "context_json": "{}"}, llm)
        assert "progress_analysis" in out

    def test_progress_tracker_handles_llm_exception(self):
        llm = ScriptedLLM({"analista de progreso": RuntimeError("x")})
        out = progress_tracker_node({"messages": [], "context_json": "{}"}, llm)
        assert out["progress_analysis"] == ""


# ---------------------------------------------------------------------------
# research_node y deep_research_node
# ---------------------------------------------------------------------------


class TestResearchNode:
    def test_research_yields_notes(self):
        llm = ScriptedLLM({"agente de research": "notas del research"})
        out = research_node(
            {"messages": [HumanMessage(content="x")], "context_json": "{}"},
            llm,
        )
        assert out["research_notes"] == "notas del research"

    def test_research_llm_exception_yields_empty(self):
        llm = ScriptedLLM({"agente de research": RuntimeError("x")})
        out = research_node({"messages": [], "context_json": "{}"}, llm)
        assert out["research_notes"] == ""

    def test_register_document_listings_invalid_json(self):
        # No revienta con json invalido.
        _register_document_listings("u", "not-json")

    def test_register_document_listings_no_user(self):
        _register_document_listings("", "{}")

    def test_register_document_listings_with_docs(self):
        ctx = json.dumps({
            "projects": [{"_id": "p1", "titulo": "P"}],
            "documents": [{"_id": "d1", "original_name": "x.txt", "project_id": "p1"}],
        })
        _register_document_listings("66ffbbbbbbbbbbbbbbbb0100", ctx)


class TestDeepResearchNode:
    def test_falls_back_when_not_requested(self):
        """Cuando deep_search_requested es False el nodo no debe devolver un
        dict vacío (rompería el grafo con InvalidUpdateError); en su lugar
        marca deep_search_error para que el router caiga a research."""
        out = deep_research_node({"deep_search_requested": False, "messages": []}, None)
        assert "no activado" in out["deep_search_error"].lower()
        assert out["deep_search_results"] == []
        assert out["deep_research_sources"] == []

    def test_returns_error_when_no_query(self):
        out = deep_research_node(
            {"deep_search_requested": True, "messages": []},
            None,
        )
        assert "deep_search_error" in out

    def test_last_user_message_text(self):
        msgs = [HumanMessage(content="primero"), HumanMessage(content="ultimo")]
        assert _last_user_message_text(msgs) == "ultimo"

    def test_last_user_message_text_empty(self):
        assert _last_user_message_text([]) == ""

    def test_runs_with_error_from_provider(self, monkeypatch):
        from ai.services.deep_search_service import DeepSearchError
        import ai.agents.deep_research as deep_research_mod

        def _boom(*a, **k):
            raise DeepSearchError("test")

        monkeypatch.setattr(deep_research_mod, "run_deep_research", _boom)
        out = deep_research_node(
            {"deep_search_requested": True, "messages": [HumanMessage(content="x")], "context_json": "{}"},
            None,
        )
        assert "deep_search_error" in out
