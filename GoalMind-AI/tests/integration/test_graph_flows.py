"""Tests end-to-end del grafo con LLM guionizado.

Cada test ejercita una ruta concreta del grafo LangGraph desde el supervisor
hasta `finalize`, con un `ScriptedLLM` que dispatch-ea por substring del
*system prompt*. Se verifican:

- Flujo CRUD con cola y resolucion de `$ref:alias` para dependencias.
- Flujo CRUD con accion destructiva: peticion de confirmacion + ejecucion
  tras un segundo turno.
- Flujo research interno (no requiere deep search).
- Flujo deep_research con *fallback* a research cuando no hay deep_search
  configurado.
- Flujo documental: read (summary) y write_note.
- `finalize` como unico punto de salida del grafo.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from bson import ObjectId

from tests._fakes import (
    ScriptedLLM,
    action_planner_response,
    supervisor_response,
)

pytestmark = pytest.mark.integration

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"


def _consume_stream(message, deep_search_mode=None):
    """Ejecuta `stream_chat` y devuelve la lista completa de eventos."""
    from ai.chat import stream_chat

    return list(stream_chat(message, [], deep_search_mode=deep_search_mode))


def _final_reply(events):
    for e_type, data in events:
        if e_type == "done":
            return data.get("reply", "")
    return ""


def _node_keys_traversed(events):
    """`name` del NODE_STATUS por cada evento status (para verificar el orden)."""
    return [data.get("name") for e_type, data in events if e_type == "status"]


class TestCrudQueueWithRefAlias:
    """Flujo CRUD con cola multi-accion y dependencias via `$ref:alias`."""

    def test_creates_project_goal_and_task_resolving_refs(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        actions = [
            {
                "action_name": "create_project",
                "action_parameters": {"titulo": "TFG"},
                "ref_id": "p1",
            },
            {
                "action_name": "create_goal",
                "action_parameters": {"titulo": "redactar", "project_id": "$ref:p1"},
                "ref_id": "g1",
            },
            {
                "action_name": "create_task",
                "action_parameters": {"contenido": "intro", "goal_id": "$ref:g1"},
            },
        ]
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
        })
        patch_llm(llm)

        events = _consume_stream("crea proyecto TFG con objetivo redactar y tarea intro")

        # Hay un proyecto, un objetivo y una tarea en la BD local.
        assert mongo_mock.local_db["Projects"].count_documents({"titulo": "TFG"}) == 1
        goal = mongo_mock.local_db["Goals"].find_one({"titulo": "redactar"})
        task = mongo_mock.local_db["Tasks"].find_one({"contenido": "intro"})
        assert goal is not None and task is not None

        # El goal apunta al proyecto resuelto via ref:p1
        project = mongo_mock.local_db["Projects"].find_one({"titulo": "TFG"})
        assert str(goal["project_id"]) == str(project["_id"])
        # La tarea apunta al goal resuelto via ref:g1
        assert str(task["objetivo_id"]) == str(goal["_id"])

        # El stream incluye un evento done (no error).
        types = [t for t, _ in events]
        assert types.count("done") == 1
        assert types.count("error") == 0


class TestDestructiveActionConfirmation:
    """Una accion destructiva pide confirmacion antes de ejecutarse."""

    def test_first_turn_asks_for_confirmation_without_deleting(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        project_id = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id,
            "titulo": "old",
            "usuario_id": USER_ID_STR,
        })

        actions = [{
            "action_name": "delete_project",
            "action_parameters": {"titulo": "old"},
        }]
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
        })
        patch_llm(llm)

        events = _consume_stream("borra el proyecto old")
        reply = _final_reply(events)

        assert "confirm" in reply.lower() or "destructiv" in reply.lower()
        # El proyecto sigue intacto.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is not None

    def test_second_turn_with_confirm_executes_the_queue(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        from ai.services.action_state import get_pending_action

        project_id = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id,
            "titulo": "old",
            "usuario_id": USER_ID_STR,
        })

        # Nota: el action_planner real resuelve nombres a IDs usando el
        # contexto cargado por el supervisor. En el segundo turno la
        # confirmacion entra directamente al supervisor->queue_executor
        # sin volver a cargar contexto, asi que las acciones encoladas
        # deben ya llevar `project_id` (no solo `titulo`) para que
        # action_executor pueda resolverlas.
        actions = [{
            "action_name": "delete_project",
            "action_parameters": {"project_id": str(project_id)},
        }]
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
            "Hay una accion pendiente": json.dumps({"intent": "confirm"}),
        })
        patch_llm(llm)

        _consume_stream("borra el proyecto old")
        # Estado: hay una accion pendiente para nuestro usuario.
        pending = get_pending_action(USER_ID_STR)
        assert pending is not None
        assert pending["action_name"] == "__queue__"

        # ── Turno 2: 'confirmo' ──
        _consume_stream("confirmo")
        # El proyecto ya no esta.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is None
        # Y la accion pendiente se ha consumido.
        assert get_pending_action(USER_ID_STR) is None


class TestResearchFlow:
    """Flujo de research interno: supervisor → research → writer → finalize."""

    def test_research_flow_produces_final_reply(self, patch_llm, scripted_llm):
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("research"),
            "agente de research": "notas internas del agente research",
            "agente writer": "respuesta final del writer",
        })
        patch_llm(llm)

        events = _consume_stream("dime que productos hay")
        assert _final_reply(events) == "respuesta final del writer"
        # El nodo finalize debe haberse activado.
        assert "Finalizador" in _node_keys_traversed(events)


class TestWeeklySummaryFallback:
    """El resumen semanal debe responder aunque el LLM falle en ese nodo."""

    def test_weekly_summary_uses_metrics_fallback_when_llm_fails(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        now = datetime.utcnow()
        mongo_mock.local_db["Tasks"].insert_many(
            [
                {
                    "_id": ObjectId(),
                    "contenido": "Cerrada esta semana",
                    "estado": "completada",
                    "fecha_limite": now,
                    "updated_at": now,
                    "usuario_id": USER_ID_STR,
                },
                {
                    "_id": ObjectId(),
                    "contenido": "Pendiente hoy",
                    "estado": "pendiente",
                    "fecha_limite": now,
                    "prioridad": "alta",
                    "usuario_id": USER_ID_STR,
                },
            ]
        )
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("weekly_summary"),
            "resumen de la semana": RuntimeError("LLM down"),
        })
        patch_llm(llm)

        events = _consume_stream("Hazme un resumen de la semana")
        reply = _final_reply(events)

        assert "Resumen semanal" in reply
        assert "No pude generar" not in reply
        assert "completaste" in reply


class TestRecommendationsFallback:
    """Las recomendaciones deben responder aunque falle el LLM en ese nodo."""

    def test_recommendations_uses_context_fallback_when_llm_fails(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        now = datetime.utcnow()
        mongo_mock.local_db["Tasks"].insert_one(
            {
                "_id": ObjectId(),
                "contenido": "Preparar demo",
                "estado": "pendiente",
                "prioridad": "alta",
                "fecha_limite": now,
                "usuario_id": USER_ID_STR,
            }
        )
        mongo_mock.local_db["Projects"].insert_one(
            {
                "_id": ObjectId(),
                "titulo": "TFG",
                "estado": "activo",
                "progreso": 0,
                "usuario_id": USER_ID_STR,
            }
        )
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("recommendations"),
            "recomendaciones personales": RuntimeError("LLM down"),
        })
        patch_llm(llm)

        events = _consume_stream("Dame recomendaciones personales")
        reply = _final_reply(events)

        assert "Recomendaciones personales" in reply
        assert "Preparar demo" in reply
        assert "No pude generar" not in reply


class TestDeepResearchFallback:
    """Si deep_research falla, el router cae a `research`."""

    def test_falls_back_to_research_when_provider_fails(
        self, patch_llm, scripted_llm, monkeypatch
    ):
        # Forzamos deep_search activo y mockeamos el proveedor para que falle.
        monkeypatch.setenv("DEEP_SEARCH_ENABLED", "1")
        monkeypatch.setenv("DEEP_SEARCH_PROVIDER", "tavily")
        monkeypatch.setenv("DEEP_SEARCH_API_KEY", "fake-key")

        from ai.services.deep_search_service import DeepSearchError
        import ai.agents.deep_research as deep_research_agent

        def _broken_run(*_args, **_kwargs):
            raise DeepSearchError("proveedor no disponible (test)")

        monkeypatch.setattr(deep_research_agent, "run_deep_research", _broken_run)

        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("deep_research"),
            "agente de research": "notas (fallback)",
            "agente writer": "respuesta tras fallback",
        })
        patch_llm(llm)

        events = _consume_stream("investiga a fondo el tema X", deep_search_mode="on")
        names = _node_keys_traversed(events)

        # Tanto Investigación Profunda como Investigador deberian aparecer.
        assert "Investigación Profunda" in names
        assert "Investigador" in names
        assert _final_reply(events) == "respuesta tras fallback"

    def test_falls_back_when_supervisor_routes_but_not_requested(
        self, patch_llm, scripted_llm
    ):
        """Si el supervisor clasifica ``deep_research`` pero el cliente no
        activó el modo (``deep_search_requested`` queda en False), el nodo
        debe entregar ``deep_search_error`` para que el router caiga a
        ``research`` en lugar de romper el grafo con ``InvalidUpdateError``.

        Sella el defecto detectado en la evaluación automatizada (sección
        6.4): peticiones con verbos del tipo ``investiga a fondo`` en modo
        ``auto`` clasifican como ``deep_research`` sin que el usuario haya
        activado la búsqueda externa.
        """
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("deep_research"),
            "agente de research": "notas tras fallback automático",
            "agente writer": "respuesta tras fallback automático",
        })
        patch_llm(llm)

        # Sin deep_search_mode="on" → resolved_mode = "auto" → requested=False.
        events = _consume_stream("investiga a fondo el tema X")
        names = _node_keys_traversed(events)

        # Se invoca el nodo de Investigación Profunda y a continuación cae al
        # de Investigación interna por el router de fallback.
        assert "Investigación Profunda" in names
        assert "Investigador" in names
        assert _final_reply(events) == "respuesta tras fallback automático"

        # No se ha emitido ningún evento de error en el flujo.
        types = [t for t, _ in events]
        assert "error" not in types


class TestDocumentalRead:
    """Flujo documental de lectura (summary) end-to-end."""

    def test_read_summary_invokes_doc_reader_with_summary_prompt(
        self, mongo_mock, gridfs_patch, patch_llm, scripted_llm
    ):
        from io import BytesIO

        from database import gridfs_storage

        # Seed: un proyecto y un documento con bytes en GridFS local.
        project_id = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id, "titulo": "TFG", "usuario_id": USER_ID_STR,
        })
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"contenido textual del documento"),
            original_name="nota.txt",
            content_type="text/plain",
        )
        doc_id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": doc_id,
            "project_id": project_id,
            "usuario_id": USER_ID_STR,
            "original_name": "nota.txt",
            "content_type": "text/plain",
            "size": 32,
            "local_upload_id": local_id,
            "remote_sync_pending": True,
        })

        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response(
                "document",
                doc_op="read",
                doc_read_mode="summary",
                context_needed=["projects", "documents"],
            ),
            "resolvedor de documentos": json.dumps({"doc_ids": [str(doc_id)]}),
            "resumen conciso y estructurado": "este es el resumen",
        })
        patch_llm(llm)

        events = _consume_stream("resume el documento nota.txt")
        assert _final_reply(events) == "este es el resumen"
        names = _node_keys_traversed(events)
        assert "Lector de Documentos" in names


class TestDocumentalWriteNote:
    """Flujo documental write_note: agrega una nota al unico proyecto del usuario."""

    def test_write_note_appends_note_to_project(
        self, mongo_mock, patch_llm, scripted_llm
    ):
        project_id = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id, "titulo": "TFG", "usuario_id": USER_ID_STR,
            "notas": [],
        })

        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response(
                "document",
                doc_op="write_note",
                context_needed=["projects"],
            ),
            "agente de anotaciones": "esta es mi anotacion",
        })
        patch_llm(llm)

        events = _consume_stream("añade una nota al proyecto TFG: esta es mi anotacion")
        # El proyecto ahora tiene una nota con el texto extraido por el LLM.
        project = mongo_mock.local_db["Projects"].find_one({"_id": project_id})
        assert project is not None
        notas = project.get("notas") or []
        assert len(notas) == 1
        assert notas[0]["text"] == "esta es mi anotacion"


class TestFinalizeIsTheOnlyExit:
    """Todas las rutas terminan pasando por `finalize`."""

    def test_research_path_ends_at_finalizer(self, patch_llm, scripted_llm):
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("research"),
            "agente de research": "n",
            "agente writer": "f",
        })
        patch_llm(llm)

        events = _consume_stream("pregunta")
        names = _node_keys_traversed(events)
        assert names[-1] == "Finalizador"
        # Y el done lleva un reply no vacio.
        assert _final_reply(events).strip() != ""

    def test_action_path_ends_at_finalizer(self, mongo_mock, patch_llm, scripted_llm):
        actions = [{
            "action_name": "create_project",
            "action_parameters": {"titulo": "X"},
        }]
        llm = scripted_llm({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
        })
        patch_llm(llm)

        events = _consume_stream("crea proyecto X")
        names = _node_keys_traversed(events)
        # En accion sin destructivos, las rutas que llegan al final pasan por
        # queue_executor; el final_response lo construye queue_executor (no
        # writer) y pasa directamente a finalize.
        assert "Finalizador" in names
