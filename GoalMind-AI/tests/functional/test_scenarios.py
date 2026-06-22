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
            "Crea un proyecto llamado 'TFG' con dos objetivos: 'redactar memoria' "
            "y 'preparar defensa'; y bajo el objetivo 'redactar memoria' añade tres "
            "tareas: 'intro', 'metodologia' y 'experimentacion'."
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

        prompt = (
            "Tengo tres tareas pendientes con distinta prioridad y fecha límite "
            "(una crítica que vence en dos días, una de prioridad media en cinco "
            "días y una opcional en ocho días); organízame los próximos siete días "
            "asignando cada tarea a un día concreto según su urgencia."
        )
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
        prompt_t1 = (
            "Elimina por completo el proyecto 'old' junto con todos sus objetivos, "
            "tareas y documentos asociados, pero pídeme confirmación explícita antes "
            "de tocar la base de datos."
        )
        status1, events1 = _post_chat(flask_client, prompt_t1)
        assert status1 == 200
        reply1 = _final_reply(events1)
        # El proyecto sigue ahi tras la primera peticion.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is not None
        assert "confirm" in reply1.lower() or "destructiv" in reply1.lower()

        # Turno 2: confirmar.
        prompt_t2 = "Sí, confirmo el borrado del proyecto y de todo su contenido."
        status2, events2 = _post_chat(flask_client, prompt_t2)
        assert status2 == 200
        # Cascada efectiva.
        assert mongo_mock.local_db["Projects"].find_one({"_id": project_id}) is None
        assert mongo_mock.local_db["Goals"].find_one({"_id": goal_id}) is None
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 0

        write_scenario_log(
            slug="04_borrar_con_confirmacion",
            title="Borrar un proyecto con confirmación explícita",
            user_prompts=[prompt_t1, prompt_t2],
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

        prompt = (
            "Dime qué porcentaje tengo completado del proyecto 'TFG' y cuántas "
            "tareas pendientes me quedan distribuidas por cada objetivo, indicando "
            "también el progreso individual de cada uno."
        )
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

        prompt = (
            "Crea un evento de calendario titulado 'ensayo TFG' para mañana, de "
            "10:00 a 11:00, y vincúlalo a la tarea 'presentar TFG' para que el "
            "calendario refleje el ensayo previo a la defensa."
        )
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


# ---------------------------------------------------------------------------
# Escenario 7: configurar el sistema (CU-01) — cambiar proveedor de LLM
#              y verificar que el cambio se persiste y se recoge en GET.
# ---------------------------------------------------------------------------


class TestEscenario07ConfigurarSistema:
    """CU-01. Configuración del Sistema.

    Cubre el flujo del panel de configuración: el usuario consulta los
    ajustes actuales mediante `GET /config/api/settings`, modifica el
    proveedor de IA mediante `POST /config/api/apply` y comprueba que la
    nueva configuración queda registrada en `os.environ` y se devuelve
    correctamente en la siguiente lectura. La escritura sobre el fichero
    `.env` real se desvía a un fichero temporal mediante `monkeypatch`
    para no contaminar el entorno de desarrollo.
    """

    def test_user_changes_llm_provider_via_config_panel(
        self, full_flask_client, monkeypatch, tmp_path
    ):
        import os

        from controllers import config_controller

        # Aislar la escritura del .env: redirigir ENV_PATH a un tmpfile.
        env_file = tmp_path / ".env"
        env_file.write_text(
            "LLM_PROVIDER=openai\n"
            "OPENAI_API_KEY=key-openai-valida\n"
            "GROQ_API_KEY=key-groq-valida\n"
            "GEMINI_API_KEY=key-gemini-valida\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config_controller, "ENV_PATH", env_file)

        # Desactivar la validación remota de las API keys: en un test no
        # tenemos forma de validar credenciales reales contra los proveedores.
        monkeypatch.setattr(
            config_controller, "_validate_api_keys",
            lambda *_a, **_kw: {},
        )

        # Estado de partida: el usuario está usando OpenAI.
        monkeypatch.setenv("LLM_PROVIDER", "openai")

        # Turno 1: el usuario abre el panel de configuración.
        r_get_before = full_flask_client.get("/config/api/settings")
        assert r_get_before.status_code == 200
        body_before = r_get_before.get_json()
        assert body_before["success"] is True
        ai_section_before = body_before["sections"]["ai"]
        assert ai_section_before["LLM_PROVIDER"] == "openai"

        # Turno 2: el usuario cambia el proveedor a Groq.
        prompt = (
            "Cambia el proveedor de IA del panel de configuración de OpenAI a "
            "Groq y persiste el cambio en el fichero .env del proyecto."
        )
        r_apply = full_flask_client.post(
            "/config/api/apply",
            json={"LLM_PROVIDER": "groq"},
        )
        assert r_apply.status_code == 200, r_apply.get_data(as_text=True)
        body_apply = r_apply.get_json()
        assert body_apply["success"] is True

        # La variable de entorno y el fichero quedan actualizados.
        assert os.environ["LLM_PROVIDER"] == "groq"
        env_text = env_file.read_text(encoding="utf-8")
        assert "LLM_PROVIDER=groq" in env_text

        # Turno 3: el usuario vuelve a abrir el panel y ve el cambio.
        r_get_after = full_flask_client.get("/config/api/settings")
        ai_section_after = r_get_after.get_json()["sections"]["ai"]
        assert ai_section_after["LLM_PROVIDER"] == "groq"

        write_scenario_log(
            slug="07_configurar_sistema",
            title="Configurar el sistema: cambiar el proveedor de IA",
            user_prompts=[
                "GET /config/api/settings  (abrir panel de configuración)",
                prompt,
                "GET /config/api/settings  (verificar persistencia)",
            ],
            events=[
                ("done", {"reply": f"LLM_PROVIDER antes: {ai_section_before['LLM_PROVIDER']}"}),
                ("done", {"reply": f"apply: {body_apply.get('message', '')}"}),
                ("done", {"reply": f"LLM_PROVIDER después: {ai_section_after['LLM_PROVIDER']}"}),
            ],
            db_summary={
                "ai.LLM_PROVIDER (antes)": ai_section_before["LLM_PROVIDER"],
                "ai.LLM_PROVIDER (después)": ai_section_after["LLM_PROVIDER"],
                "restart_required": body_apply.get("restart_required"),
                "env_file_contiene": "LLM_PROVIDER=groq" in env_text,
            },
            notas=(
                "Caso de uso CU-01 (Configuración del Sistema). El panel de "
                "configuración expone dos endpoints simétricos: `GET "
                "/config/api/settings` devuelve los valores actuales agrupados "
                "por sección (ai, mongo, deep_search, dev), y `POST "
                "/config/api/apply` valida y persiste los cambios en el .env y "
                "en `os.environ`. La validación remota de las API keys queda "
                "fuera del alcance del nivel funcional y se aborda en las "
                "pruebas unitarias del controlador de configuración."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 8: gestión completa de un proyecto desde la UI (CU-02)
#              sin pasar por el agente de IA: crear proyecto, añadir
#              objetivo, subir documento y añadir una nota.
# ---------------------------------------------------------------------------


class TestEscenario08GestionarProyectoViaUI:
    """CU-02. Gestión de un Proyecto.

    Recorre el flujo de gestión de un proyecto tal y como lo haría un
    usuario desde la interfaz web, atacando directamente las rutas HTTP
    correspondientes (sin pasar por `/api/ai/chat`). La prueba comprueba
    la creación del proyecto, el añadido de un objetivo, la subida de
    un documento al almacenamiento GridFS y la inserción de una nota,
    y verifica el estado final consolidado en la base de datos.
    """

    def test_user_creates_project_adds_goal_uploads_doc_and_note(
        self, full_flask_client, mongo_mock, gridfs_patch
    ):
        # ── Paso 1: el usuario crea un nuevo proyecto desde el menú lateral.
        prompt_crear = (
            "Crear desde el panel un nuevo proyecto titulado 'TFG VirtualAssistant' "
            "con la descripción 'Memoria final del Trabajo de Fin de Grado' y "
            "estado 'Activo'."
        )
        r_proj = full_flask_client.post(
            "/projects/add",
            data={
                "titulo": "TFG VirtualAssistant",
                "descripcion": "Memoria final del Trabajo de Fin de Grado",
                "estado": "Activo",
                "prioridad": "Alta",
                "usuario_id": USER_ID_STR,
            },
            follow_redirects=False,
        )
        assert r_proj.status_code in (200, 302)

        project = mongo_mock.local_db["Projects"].find_one(
            {"titulo": "TFG VirtualAssistant"}
        )
        assert project is not None
        project_id = project["_id"]

        # ── Paso 2: el usuario añade un objetivo al proyecto.
        prompt_objetivo = (
            "Añadir al proyecto 'TFG VirtualAssistant' un objetivo titulado "
            "'redactar memoria' con prioridad alta."
        )
        r_goal = full_flask_client.post(
            "/goals/add",
            data={
                "titulo": "redactar memoria",
                "project_id": str(project_id),
                "prioridad": "Alta",
                "progreso": "0",
                "usuario_id": USER_ID_STR,
            },
            follow_redirects=False,
        )
        assert r_goal.status_code in (200, 302)

        goal = mongo_mock.local_db["Goals"].find_one({"titulo": "redactar memoria"})
        assert goal is not None
        assert str(goal["project_id"]) == str(project_id)

        # ── Paso 3: el usuario adjunta un documento al proyecto.
        prompt_doc = (
            "Subir al proyecto 'TFG VirtualAssistant' el documento "
            "'plan_de_trabajo.txt' con su contenido en texto plano."
        )
        r_upload = full_flask_client.post(
            f"/projects/{project_id}/documents",
            data={
                "document": (BytesIO(b"contenido del plan de trabajo"), "plan_de_trabajo.txt"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert r_upload.status_code in (200, 302)

        doc = mongo_mock.local_db["ProjectDocuments"].find_one(
            {"original_name": "plan_de_trabajo.txt"}
        )
        assert doc is not None
        assert str(doc["project_id"]) == str(project_id)
        assert doc.get("local_upload_id") is not None

        # ── Paso 4: el usuario añade una nota textual al proyecto.
        prompt_nota = (
            "Añadir al proyecto 'TFG VirtualAssistant' la nota: "
            "'Revisar la bibliografía antes del viernes y reservar aula para la defensa.'"
        )
        r_nota = full_flask_client.post(
            f"/projects/{project_id}/notes/add",
            data={
                "note_text": (
                    "Revisar la bibliografía antes del viernes y reservar aula "
                    "para la defensa."
                ),
            },
            follow_redirects=False,
        )
        assert r_nota.status_code in (200, 302)

        project_after = mongo_mock.local_db["Projects"].find_one({"_id": project_id})
        notas = project_after.get("notas") or []
        assert len(notas) == 1
        assert "bibliografía" in notas[0]["text"]

        write_scenario_log(
            slug="08_gestionar_proyecto_via_ui",
            title="Gestionar un proyecto completo desde la interfaz web",
            user_prompts=[prompt_crear, prompt_objetivo, prompt_doc, prompt_nota],
            events=[
                ("done", {"reply": f"POST /projects/add  -> {r_proj.status_code}"}),
                ("done", {"reply": f"POST /goals/add     -> {r_goal.status_code}"}),
                ("done", {"reply": f"POST /projects/{project_id}/documents -> {r_upload.status_code}"}),
                ("done", {"reply": f"POST /projects/{project_id}/notes/add -> {r_nota.status_code}"}),
            ],
            db_summary={
                "Projects": [{
                    "titulo": project["titulo"],
                    "estado": project.get("estado"),
                    "prioridad": project.get("prioridad"),
                }],
                "Goals": [{
                    "titulo": goal["titulo"],
                    "project_id": str(goal["project_id"]),
                    "prioridad": goal.get("prioridad"),
                }],
                "ProjectDocuments": [{
                    "original_name": doc["original_name"],
                    "project_id": str(doc["project_id"]),
                    "size": doc.get("size"),
                }],
                "Projects[0].notas": [
                    {"text": n["text"][:60] + ("..." if len(n["text"]) > 60 else "")}
                    for n in notas
                ],
            },
            notas=(
                "Caso de uso CU-02 (Gestión de un Proyecto). El escenario "
                "ejercita las cuatro rutas que el frontend invoca para enriquecer "
                "un proyecto sin la intervención del agente: `POST /projects/add` "
                "crea el proyecto; `POST /goals/add` añade un objetivo; "
                "`POST /projects/<id>/documents` sube un binario al "
                "almacenamiento local de GridFS y registra su metadato en "
                "`ProjectDocuments`; y `POST /projects/<id>/notes/add` inserta "
                "una entrada en `Projects.notas[]`. Las respuestas son redirecciones "
                "HTTP 302 (comportamiento normal de las rutas pensadas para la UI)."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 9: investigación profunda con búsqueda externa simulada (CU-03)
# ---------------------------------------------------------------------------


class TestEscenario09InvestigacionProfunda:
    """CU-03. Interacción con el Asistente — Investigación profunda.

    Cuando el modo `deep_search` está activo, el supervisor enruta la
    petición al subsistema autónomo de investigación profunda. Este test
    sustituye el bucle interno por un doble determinista (`run_deep_research`
    monkeypatcheado) que devuelve notas y fuentes citadas, lo que permite
    verificar que el flujo entrega esas notas al `writer` y que la respuesta
    final del asistente las incorpora, sin necesidad de invocar a Tavily,
    Serper o Brave en una prueba.
    """

    def test_deep_research_returns_report_with_cited_sources(
        self, flask_client, patch_llm, monkeypatch
    ):

        # Activar el modo deep search a nivel de configuración.
        monkeypatch.setenv("DEEP_SEARCH_ENABLED", "1")
        monkeypatch.setenv("DEEP_SEARCH_PROVIDER", "tavily")
        monkeypatch.setenv("DEEP_SEARCH_API_KEY", "fake-key-de-test")

        # Sustituir el bucle interno por un doble determinista.
        import ai.agents.deep_research as deep_research_agent

        sources = [
            {"title": "GTD original", "url": "https://example.org/gtd-overview"},
            {"title": "Pomodoro: estado del arte", "url": "https://example.edu/pomodoro-review"},
        ]
        notes = (
            "El método GTD (Getting Things Done) prioriza el vaciado mental "
            "[1]. La técnica Pomodoro complementa GTD con bloques de "
            "concentración de 25 minutos [2]."
        )

        def _stubbed_run_deep_research(*_args, **_kwargs):
            from ai.deep_research.types import DeepResearchResult

            return DeepResearchResult(
                report=notes,
                sources=sources,
                raw_results=[],
                plan=[{"id": "t1", "title": "Comparar metodologías GTD y Pomodoro"}],
                iterations=[
                    {"task": "t1", "evidence_added": 2, "queries": ["gtd review", "pomodoro review"]},
                    {"task": "t1", "evidence_added": 1, "queries": ["time blocking eficacia"]},
                ],
                warnings=[],
            )

        monkeypatch.setattr(deep_research_agent, "run_deep_research", _stubbed_run_deep_research)

        final_text = (
            "Síntesis: el método GTD ayuda a vaciar la mente de tareas pendientes [1] "
            "y la técnica Pomodoro complementa GTD con bloques de 25 minutos de "
            "concentración [2]."
        )

        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response("deep_research"),
            "agente writer": final_text,
        })
        patch_llm(llm)

        prompt = (
            "Investiga a fondo en internet las metodologías de gestión del tiempo "
            "más eficaces para estudiantes universitarios (GTD, Pomodoro y "
            "time-blocking) y entrégame un informe sintético con fuentes citadas."
        )

        resp = flask_client.post(
            "/api/ai/chat",
            json={"message": prompt, "deep_search_mode": "on"},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.get_data(as_text=True))
        reply = _final_reply(events)

        # La respuesta final del writer incorpora las referencias.
        assert "[1]" in reply or "GTD" in reply
        # El nodo de investigación profunda aparece en el flujo emitido al cliente.
        node_names = [data.get("name", "") for e_type, data in events if e_type == "status"]
        assert any("Investigación Profunda" in n or "Investigador" in n for n in node_names)

        write_scenario_log(
            slug="09_investigacion_profunda",
            title="Investigación profunda con fuentes externas",
            user_prompts=[prompt],
            events=events,
            db_summary={
                "deep_research.iterations": 2,
                "deep_research.sources": sources,
                "deep_research.plan": [{"id": "t1", "title": "Comparar metodologías GTD y Pomodoro"}],
                "writer.final_reply": reply[:200],
            },
            notas=(
                "Caso de uso CU-03 (Investigación Profunda). El supervisor "
                "clasifica la petición como `deep_research` porque el cliente "
                "envía `deep_search_mode='on'`. El subsistema autónomo "
                "(Planner-Researcher-Analyzer-Reporter) se sustituye por un "
                "doble determinista en este nivel, dado que el bucle real "
                "incurre en hasta seis iteraciones contra el proveedor de "
                "búsqueda externo. Las dos referencias `[1]` y `[2]` que "
                "produce el reporter se trasladan al `writer`, que las "
                "incorpora en la respuesta final entregada al usuario."
            ),
        )


# ---------------------------------------------------------------------------
# Escenario 10: recomendaciones de priorización (CU-03)
# ---------------------------------------------------------------------------


class TestEscenario10RecomendacionesPriorizacion:
    """CU-03. Interacción con el Asistente — Recomendaciones.

    Cuando el supervisor clasifica una petición como `recommendations`, el
    agente especializado del mismo nombre carga el contexto del usuario y
    produce directamente la respuesta priorizada que el flujo entrega al
    cliente (en este flujo, a diferencia de `research`, el grafo no
    atraviesa el nodo `writer`). La prueba comprueba que el contexto
    cargado por el supervisor llega al agente, que el agente produce el
    texto priorizado y que la respuesta final del usuario lo refleja.
    """

    def test_recommendations_agent_proposes_priorities(
        self, flask_client, patch_llm, mongo_mock
    ):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        # Seed: cinco tareas con prioridad y fecha límite distintas.
        tasks_seed = [
            {"_id": ObjectId(), "contenido": "preparar slides",
             "prioridad": "alta", "estado": "pendiente",
             "fecha_limite": now + timedelta(days=1), "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "redactar conclusiones",
             "prioridad": "alta", "estado": "pendiente",
             "fecha_limite": now + timedelta(days=3), "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "revisar bibliografia",
             "prioridad": "media", "estado": "pendiente",
             "fecha_limite": now + timedelta(days=5), "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "ensayar defensa",
             "prioridad": "alta", "estado": "pendiente",
             "fecha_limite": now + timedelta(days=6), "usuario_id": USER_ID_STR},
            {"_id": ObjectId(), "contenido": "actualizar CV",
             "prioridad": "baja", "estado": "pendiente",
             "fecha_limite": now + timedelta(days=14), "usuario_id": USER_ID_STR},
        ]
        mongo_mock.local_db["Tasks"].insert_many(tasks_seed)

        recommendation_reply = (
            "RECOMENDACIONES DE PRIORIZACIÓN:\n"
            "1) preparar slides (alta, vence mañana)\n"
            "2) redactar conclusiones (alta, vence en 3 días)\n"
            "3) ensayar defensa (alta, vence en 6 días)\n"
            "4) revisar bibliografia (media, vence en 5 días)\n"
            "5) actualizar CV (baja, vence en 14 días)"
        )

        llm = ScriptedLLM({
            "supervisor de GoalMind AI": supervisor_response(
                "recommendations",
                context_needed=["tasks", "projects", "goals"],
            ),
            "agente de recomendaciones personales": recommendation_reply,
        })
        patch_llm(llm)

        prompt = (
            "Tengo cinco tareas pendientes esta semana con prioridades distintas "
            "(alta, media y baja) y fechas límite escalonadas; recomiéndame en qué "
            "orden las debería abordar para llegar a tiempo a la defensa del TFG."
        )

        status, events = _post_chat(flask_client, prompt)
        assert status == 200
        reply = _final_reply(events)

        # Se invocaron los agentes esperados y la respuesta menciona alguna tarea.
        captured = "\n".join(c["system_text"] for c in llm.calls)
        assert "agente de recomendaciones personales" in captured
        assert "preparar slides" in reply or "preparar slides" in captured

        # El supervisor enrutó por la categoría recommendations: aparece el Asesor
        # y luego se cierra el flujo en el Finalizador, sin pasar por el Redactor.
        node_names = [data.get("name", "") for e_type, data in events if e_type == "status"]
        assert "Asesor" in node_names
        assert "Finalizador" in node_names
        assert "Redactor" not in node_names

        write_scenario_log(
            slug="10_recomendaciones_priorizacion",
            title="Recomendaciones de priorización de tareas",
            user_prompts=[prompt],
            events=events,
            db_summary={
                "Tasks seed (5)": [
                    {"contenido": t["contenido"], "prioridad": t["prioridad"]}
                    for t in tasks_seed
                ],
                "writer.final_reply": reply[:200],
            },
            notas=(
                "Caso de uso CU-03 (Recomendaciones). El supervisor clasifica "
                "la petición como `recommendations`, carga el contexto de "
                "tareas, proyectos y objetivos y lo entrega al agente "
                "especializado, que pondera prioridad y fecha límite para "
                "producir el orden recomendado. A diferencia del flujo de "
                "`research`, en este flujo el grafo no atraviesa el nodo "
                "`writer`: la respuesta del agente Asesor llega directamente "
                "al nodo de finalización (ver `_route_after_writer` en "
                "`ai/graph.py`, que enruta a `critic` o `finalize` según "
                "`use_critic`)."
            ),
        )
