"""Validacion funcional: 6 escenarios end-to-end de uso real del asistente.

Cada test:
  1. Prepara una BD de partida (mongomock + GridFS in-memory).
  2. Manda peticiones HTTP reales al *test client* de Flask, simulando lo que
     haria el frontend (`/api/ai/chat` o `/api/ai/summarize-document`).
  3. Verifica tanto la respuesta como el estado final en BD.
  4. Exporta un log legible a `docs/tfg/escenarios/<slug>.md` con: prompt
     del usuario, eventos SSE emitidos y resumen del estado final.

Los logs estan pensados para pegarse literalmente en la memoria del TFG.
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from bson import ObjectId

from tests._fakes import (
    ScriptedLLM,
    action_planner_response,
    supervisor_response,
)
from tests.functional.conftest import write_scenario_log

pytestmark = pytest.mark.functional

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"


# ---------------------------------------------------------------------------
# Utilidades comunes (un nivel mas finas que las de tests/integration/*)
# ---------------------------------------------------------------------------


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk.startswith("data:"):
            continue
        payload = json.loads(chunk[len("data:") :].strip())
        e_type = payload.pop("type", "?")
        out.append((e_type, payload))
    return out


def _post_chat(client, message: str) -> tuple[int, list[tuple[str, dict]]]:
    resp = client.post("/api/ai/chat", json={"message": message})
    events = _parse_sse(resp.get_data(as_text=True)) if resp.status_code == 200 else []
    return resp.status_code, events


def _final_reply(events: list[tuple[str, dict]]) -> str:
    for e_type, data in events:
        if e_type == "done":
            return data.get("reply", "")
    return ""


# ---------------------------------------------------------------------------
# Escenario 1: crear un proyecto + 2 objetivos + 3 tareas en un solo prompt
# ---------------------------------------------------------------------------


class TestEscenario01CrearProyectoCompleto:

    def test_creates_full_hierarchy_in_a_single_prompt(
        self, flask_client, patch_llm, mongo_mock
    ):
        # Como el agente real resolveria $ref antes de ejecutar, el
        # action_planner devuelve ya las acciones con ref_id y referencias
        # via $ref:alias entre acciones.
        actions = [
            {"action_name": "create_project", "action_parameters": {"titulo": "TFG"}, "ref_id": "p1"},
            {"action_name": "create_goal", "action_parameters": {"titulo": "redactar memoria", "project_id": "$ref:p1"}, "ref_id": "g_y"},
            {"action_name": "create_goal", "action_parameters": {"titulo": "preparar defensa", "project_id": "$ref:p1"}, "ref_id": "g_z"},
            {"action_name": "create_task", "action_parameters": {"contenido": "intro", "goal_id": "$ref:g_y"}},
            {"action_name": "create_task", "action_parameters": {"contenido": "metodologia", "goal_id": "$ref:g_y"}},
            {"action_name": "create_task", "action_parameters": {"contenido": "experimentacion", "goal_id": "$ref:g_y"}},
        ]
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
        })
        patch_llm(llm)

        prompt = (
            "crea un proyecto TFG con dos objetivos 'redactar memoria' y "
            "'preparar defensa', y tres tareas (intro, metodologia, experimentacion) "
            "bajo 'redactar memoria'"
        )
        status, events = _post_chat(flask_client, prompt)
        assert status == 200

        project = mongo_mock.local_db["Projects"].find_one({"titulo": "TFG"})
        goals = list(mongo_mock.local_db["Goals"].find().sort("titulo", 1))
        tasks = list(mongo_mock.local_db["Tasks"].find().sort("contenido", 1))

        assert project is not None
        assert {g["titulo"] for g in goals} == {"redactar memoria", "preparar defensa"}
        # Los dos goals apuntan al mismo proyecto.
        assert all(str(g["project_id"]) == str(project["_id"]) for g in goals)
        # Las tres tareas apuntan al goal "redactar memoria".
        redactar = next(g for g in goals if g["titulo"] == "redactar memoria")
        assert {t["contenido"] for t in tasks} == {"intro", "metodologia", "experimentacion"}
        assert all(str(t["objetivo_id"]) == str(redactar["_id"]) for t in tasks)

        write_scenario_log(
            slug="01_crear_proyecto_completo",
            title="Crear proyecto con objetivos y tareas en un único prompt",
            user_prompts=[prompt],
            events=events,
            db_summary={
                "Projects": [{"titulo": project["titulo"], "_id": str(project["_id"])}],
                "Goals": [
                    {"titulo": g["titulo"], "project_id": str(g["project_id"])} for g in goals
                ],
                "Tasks": [
                    {"contenido": t["contenido"], "objetivo_id": str(t["objetivo_id"])}
                    for t in tasks
                ],
            },
            notas=(
                "Demuestra el flujo CRUD multi-accion con resolucion de `$ref:alias` entre "
                "acciones encoladas: el `goal` referencia al `project` recien creado, y "
                "las tareas referencian al `goal` recien creado."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 2: replanificar la semana sobre tareas pendientes
# ---------------------------------------------------------------------------


class TestEscenario02ReplanificarSemana:

    def test_weekly_planner_receives_context_and_produces_plan(
        self, flask_client, patch_llm, mongo_mock
    ):
        # Seed: 3 tareas con prioridades y fechas.
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        tasks_seed = [
            {"_id": ObjectId(), "contenido": "tarea critica", "prioridad": "alta",
             "fecha_limite": now + timedelta(days=2), "estado": "pendiente",
             "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "tarea normal", "prioridad": "media",
             "fecha_limite": now + timedelta(days=5), "estado": "pendiente",
             "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "tarea opcional", "prioridad": "baja",
             "fecha_limite": now + timedelta(days=8), "estado": "pendiente",
             "usuario_id": USER_ID_STR},
        ]
        mongo_mock.local_db["Tasks"].insert_many(tasks_seed)

        plan_text = (
            "PLAN SEMANAL\n"
            "1) Lunes: tarea critica (alta prioridad, vence en 2 dias)\n"
            "2) Miercoles: tarea normal\n"
            "3) Viernes: tarea opcional"
        )

        # Tras supervisor->weekly_planner, NO pasa por writer (ver graph.py).
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response(
                "weekly_plan",
                context_needed=["tasks", "goals", "projects"],
            ),
            "planificador semanal de GoalMind AI": plan_text,
        })
        patch_llm(llm)

        prompt = "planifica mi proxima semana priorizando lo mas urgente"
        status, events = _post_chat(flask_client, prompt)
        assert status == 200
        reply = _final_reply(events)
        assert "PLAN SEMANAL" in reply
        # El planner recibio el contexto que el supervisor cargo: alguno de los
        # contenidos de las tareas debe aparecer en el system prompt visto por
        # el LLM (capturado por ScriptedLLM.calls).
        captured = "\n".join(c["system_text"] for c in llm.calls)
        assert "tarea critica" in captured

        write_scenario_log(
            slug="02_replanificar_semana",
            title="Replanificar la semana sobre tareas pendientes",
            user_prompts=[prompt],
            events=events,
            db_summary={"Tasks": [{"contenido": t["contenido"], "prioridad": t["prioridad"]} for t in tasks_seed]},
            notas=(
                "El supervisor carga el contexto (`tasks, goals, projects`) y lo pasa al "
                "`weekly_planner`. La calidad del plan que produzca el LLM real se evalua "
                "en el bloque 5.4 con metricas concretas; aqui solo verificamos que el "
                "flujo se invoca, recibe los datos y la respuesta cumple el contrato minimo."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 3: resumir un documento via /api/ai/summarize-document
# ---------------------------------------------------------------------------


class TestEscenario03ResumirDocumento:

    def test_summarize_endpoint_creates_note_in_project(
        self, flask_client, patch_llm, mongo_mock, gridfs_patch
    ):
        from database import gridfs_storage

        # Seed: proyecto + documento + bytes en GridFS local.
        project_id = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id, "titulo": "TFG", "usuario_id": USER_ID_STR, "notas": [],
        })
        local_upload_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"este es el contenido textual del documento de prueba"),
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
            "size": 50,
            "local_upload_id": local_upload_id,
            "remote_sync_pending": True,
        })

        # `summarize_and_save_note` invoca `doc_reader_node` en modo summary
        # via DOC_READER_SUMMARY_PROMPT.
        llm = ScriptedLLM({
            "resumen conciso y estructurado": "Resumen del documento: tres puntos clave.",
        })
        patch_llm(llm)

        resp = flask_client.post(
            "/api/ai/summarize-document",
            json={"doc_id": str(doc_id), "project_id": str(project_id)},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["success"] is True
        assert "nota" in body["message"].lower()

        # El proyecto ahora tiene exactamente una nota con el resumen.
        project = mongo_mock.local_db["Projects"].find_one({"_id": project_id})
        notas = project.get("notas") or []
        assert len(notas) == 1
        assert "Resumen del documento" in notas[0]["text"]
        assert "[Resumen automático" in notas[0]["text"]

        # Este escenario no usa /api/ai/chat: no hay eventos SSE.
        write_scenario_log(
            slug="03_resumir_documento",
            title="Resumir un documento subido a un proyecto",
            user_prompts=[
                "POST /api/ai/summarize-document",
                f"  body = {{'doc_id': '{doc_id}', 'project_id': '{project_id}'}}",
            ],
            events=[("done", body)],
            db_summary={
                "Projects[0].notas[0]": {
                    "text": notas[0]["text"][:80] + "...",
                    "created_at": str(notas[0]["created_at"]),
                },
            },
            notas=(
                "El endpoint `/api/ai/summarize-document` no usa el grafo: invoca "
                "directamente `summarize_and_save_note`, que reusa `doc_reader_node` en "
                "modo `summary` para generar el texto y luego lo persiste como nota del "
                "proyecto. La nota lleva el prefijo `[Resumen automático de '<nombre>']`."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 4: borrar un proyecto con confirmacion (cascada)
# ---------------------------------------------------------------------------


class TestEscenario04BorrarConConfirmacion:

    def test_destructive_action_two_turns_and_cascade(
        self, flask_client, patch_llm, mongo_mock
    ):
        # Seed: proyecto con un objetivo y dos tareas.
        project_id = ObjectId()
        goal_id = ObjectId()
        task_a = ObjectId()
        task_b = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id, "titulo": "old", "usuario_id": USER_ID_STR,
        })
        mongo_mock.local_db["Goals"].insert_one({
            "_id": goal_id, "titulo": "obj", "project_id": project_id, "usuario_id": USER_ID_STR,
        })
        mongo_mock.local_db["Tasks"].insert_many([
            {"_id": task_a, "contenido": "a", "objetivo_id": goal_id, "usuario_id": USER_ID_STR},
            {"_id": task_b, "contenido": "b", "objetivo_id": goal_id, "usuario_id": USER_ID_STR},
        ])

        actions = [{
            "action_name": "delete_project",
            "action_parameters": {"project_id": str(project_id)},
        }]
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
            "Hay una accion pendiente": json.dumps({"intent": "confirm"}),
        })
        patch_llm(llm)

        # Turno 1: pedir el borrado.
        status1, events1 = _post_chat(flask_client, "borra el proyecto old")
        assert status1 == 200
        reply1 = _final_reply(events1)
        # El proyecto sigue ahi tras la primera peticion.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is not None
        assert "confirm" in reply1.lower() or "destructiv" in reply1.lower()

        # Turno 2: confirmar.
        status2, events2 = _post_chat(flask_client, "confirmo")
        assert status2 == 200
        # Cascada efectiva.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is None
        assert mongo_mock.local_db["Goals"].find_one({"_id": goal_id}) is None
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 0

        write_scenario_log(
            slug="04_borrar_con_confirmacion",
            title="Borrar un proyecto con confirmación explícita",
            user_prompts=["borra el proyecto old", "confirmo"],
            events=events1 + [("--- siguiente turno ---", {})] + events2,
            db_summary={
                "Projects": list(mongo_mock.local_db["Projects"].find()),
                "Goals": list(mongo_mock.local_db["Goals"].find()),
                "Tasks": list(mongo_mock.local_db["Tasks"].find()),
                "DeleteQueue (collections)": list(
                    {d["collection"] for d in mongo_mock.local_db["DeleteQueue"].find()}
                ),
            },
            notas=(
                "El primer turno deja la cola en `_pending_actions` y emite un mensaje "
                "de confirmacion sin tocar la BD. El segundo turno ('confirmo') entra al "
                "supervisor por la fase de *pending action*, clasifica con "
                "`PENDING_ACTION_PROMPT` y enruta a `queue_executor` para ejecutar la "
                "cascada via `_delete_project_cascade`."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 5: consultar progreso con tareas en distintos estados
# ---------------------------------------------------------------------------


class TestEscenario05ConsultarProgreso:

    def test_progress_tracker_receives_full_hierarchy(
        self, flask_client, patch_llm, mongo_mock
    ):
        project_id = ObjectId()
        goal1 = ObjectId()
        goal2 = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": project_id, "titulo": "TFG", "usuario_id": USER_ID_STR,
        })
        mongo_mock.local_db["Goals"].insert_many([
            {"_id": goal1, "titulo": "G1", "project_id": project_id, "progreso": 75, "usuario_id": USER_ID_STR},
            {"_id": goal2, "titulo": "G2", "project_id": project_id, "progreso": 25, "usuario_id": USER_ID_STR},
        ])
        mongo_mock.local_db["Tasks"].insert_many([
            {"_id": ObjectId(), "contenido": "t1", "objetivo_id": goal1, "estado": "completada", "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "t2", "objetivo_id": goal1, "estado": "completada", "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "t3", "objetivo_id": goal1, "estado": "pendiente", "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "t4", "objetivo_id": goal2, "estado": "pendiente", "usuario_id": USER_ID_STR},
        ])

        analysis = (
            "RESUMEN GLOBAL: 50% (media de progresos).\n"
            "PROYECTO TFG: G1=75% (2/3 tareas completadas), G2=25% (0/1 tareas)."
        )
        final = (
            "Estado del TFG: 50% de avance medio. G1 va al 75% (2 de 3 completadas), "
            "G2 al 25% (0 de 1)."
        )
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response(
                "progress",
                context_needed=["projects", "goals", "tasks"],
            ),
            "analista de progreso de GoalMind AI": analysis,
            "agente writer": final,
        })
        patch_llm(llm)

        prompt = "como va mi progreso?"
        status, events = _post_chat(flask_client, prompt)
        assert status == 200
        reply = _final_reply(events)
        assert "50%" in reply or "progreso" in reply.lower()

        # Verifica que el progress_tracker recibio el contexto cargado.
        capt = "\n".join(c["system_text"] for c in llm.calls)
        assert "G1" in capt or "G2" in capt

        write_scenario_log(
            slug="05_consultar_progreso",
            title="Consultar el progreso del proyecto",
            user_prompts=[prompt],
            events=events,
            db_summary={
                "Projects": [{"titulo": "TFG"}],
                "Goals": [{"titulo": "G1", "progreso": 75}, {"titulo": "G2", "progreso": 25}],
                "Tasks por estado": {
                    "completada": mongo_mock.local_db["Tasks"].count_documents({"estado": "completada"}),
                    "pendiente": mongo_mock.local_db["Tasks"].count_documents({"estado": "pendiente"}),
                },
            },
            notas=(
                "El `progress_tracker` produce un texto de analisis (`progress_analysis`) "
                "que el `writer` consume para componer la respuesta final del usuario. "
                "Los porcentajes de cada objetivo provienen del campo `progreso` "
                "(`ProjectModel.calculate_progress_from_goals` los promedia)."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 6: crear un evento asociado a una tarea via chat
# ---------------------------------------------------------------------------


class TestEscenario06CrearEventoAsociado:

    def test_event_creation_via_chat_persists_id_tarea(
        self, flask_client, patch_llm, mongo_mock
    ):
        # Seed: una tarea referenciable.
        task_id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({
            "_id": task_id, "contenido": "presentar TFG",
            "usuario_id": USER_ID_STR, "event_ids": [],
        })

        actions = [{
            "action_name": "create_event",
            "action_parameters": {
                "titulo": "ensayo TFG",
                "fecha_inicio": "2026-05-17T10:00:00Z",
                "fecha_fin": "2026-05-17T11:00:00Z",
                "id_tarea": str(task_id),
            },
        }]
        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response("action"),
            "planificador de acciones": action_planner_response(actions),
        })
        patch_llm(llm)

        prompt = "crea un evento mañana a las 10 para la tarea presentar TFG"
        status, events = _post_chat(flask_client, prompt)
        assert status == 200

        # El evento existe con id_tarea apuntando a la tarea.
        event = mongo_mock.local_db["Events"].find_one({"titulo": "ensayo TFG"})
        assert event is not None
        assert str(event.get("id_tarea")) == str(task_id)

        # ── Hallazgo ─────────────────────────────────────────────────
        # Via /api/ai/chat (agente), el evento se persiste con campo `id_tarea`
        # y la tarea NO recibe el event_id en su `event_ids[]`. La ruta HTTP
        # `POST /api/events` (calendar_controller) hace lo contrario: usa
        # `referencia_tipo`/`referencia_id` y ACTUALIZA `event_ids` via
        # `_sync_event_association`. Es una inconsistencia de schema entre las
        # dos rutas; aqui se documenta tal y como ocurre.
        task = mongo_mock.local_db["Tasks"].find_one({"_id": task_id})
        assert task["event_ids"] == [], (
            "Via agente, event_ids no se actualiza (la sincronizacion solo se hace "
            "en el calendar_controller)."
        )

        write_scenario_log(
            slug="06_crear_evento_asociado",
            title="Crear un evento asociado a una tarea (vía chat)",
            user_prompts=[prompt],
            events=events,
            db_summary={
                "Events": [{
                    "titulo": event["titulo"],
                    "fecha_inicio": str(event.get("fecha_inicio")),
                    "id_tarea": str(event.get("id_tarea")),
                    "referencia_tipo": event.get("referencia_tipo"),
                    "referencia_id": event.get("referencia_id"),
                }],
                "Tasks (event_ids)": {
                    "presentar TFG": task.get("event_ids"),
                },
            },
            notas=(
                "**HALLAZGO**: hay dos schemas para los eventos. Por la via HTTP "
                "(`POST /api/events`, `calendar_controller`), un evento usa `referencia_tipo` "
                "('tarea'|'objetivo') + `referencia_id` (ObjectId) y la tarea/objetivo "
                "asociado recibe el `event_id` en su `event_ids[]` via `_sync_event_association`. "
                "Por la via *chat* (`action_executor.create_event`), el evento usa los "
                "campos legacy `id_tarea`/`id_objetivo` y no actualiza `event_ids` en la "
                "tarea. Las dos rutas producen documentos con esquemas distintos, lo que "
                "rompera consultas que asuman uno u otro modelo."
            ),
        )
