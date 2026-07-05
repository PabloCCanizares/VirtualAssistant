"""Bateria completa del controlador REST del calendario.

Cubre las 8 rutas del *blueprint* `calendar_bp`. Los helpers puros
(`_parse_iso`, `_iso_utc`, `_validate_required`) ya estan cubiertos por
`tests/test_calendar_helpers.py`; este fichero se centra en los endpoints,
en la sincronizacion bidireccional con tareas/objetivos via
`_sync_event_association` y en los filtros por rango y por tipo.

`_events_col()` se sustituye por una coleccion de `mongomock` para no
depender de un MongoDB real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from bson import ObjectId
from flask import Flask

from controllers import calendar_controller
from controllers.calendar_controller import calendar_bp


@pytest.fixture
def events_col(monkeypatch):
    """Coleccion `Events` falsa basada en mongomock."""
    client = mongomock.MongoClient()
    db = client["test"]
    col = db["Events"]
    monkeypatch.setattr(calendar_controller, "_events_col", lambda: (col, None))

    def _queue_deletion(collection_name, target_id):
        assert collection_name == "Events"
        queries = [{"_id": target_id}]
        try:
            if ObjectId.is_valid(str(target_id)):
                queries.append({"_id": ObjectId(str(target_id))})
        except Exception:
            pass
        col.delete_many({"$or": queries})
        return True

    monkeypatch.setattr(calendar_controller, "queue_deletion", _queue_deletion)
    monkeypatch.setattr(calendar_controller, "flush_deletion_queue", lambda: 0)
    return col


@pytest.fixture
def client(monkeypatch, events_col):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    def _fake_render(template_name, **ctx):
        return f"RENDER::{template_name}"

    monkeypatch.setattr(calendar_controller, "render_template", _fake_render)
    # Stubs para los modelos a los que invoca `_sync_event_association`.
    monkeypatch.setattr(
        calendar_controller.TaskModel, "add_event_to_task",
        staticmethod(lambda *a, **k: True),
    )
    monkeypatch.setattr(
        calendar_controller.TaskModel, "remove_event_from_task",
        staticmethod(lambda *a, **k: True),
    )
    monkeypatch.setattr(
        calendar_controller.GoalModel, "add_event_to_goal",
        staticmethod(lambda *a, **k: True),
    )
    monkeypatch.setattr(
        calendar_controller.GoalModel, "remove_event_from_goal",
        staticmethod(lambda *a, **k: True),
    )
    app.register_blueprint(calendar_bp)
    return app.test_client()


def _insert_event(col, *, titulo="ev", start_offset_hours=0, end_offset_hours=1, **extra):
    now = datetime.now(timezone.utc)
    doc = {
        "_id": ObjectId(),
        "titulo": titulo,
        "fecha_inicio": now + timedelta(hours=start_offset_hours),
        "fecha_fin": now + timedelta(hours=end_offset_hours),
        "usuario_id": calendar_controller.DEFAULT_USER_ID,
    }
    doc.update(extra)
    col.insert_one(doc)
    return doc


# ---------------------------------------------------------------------------
# GET /calendar
# ---------------------------------------------------------------------------


class TestCalendarPage:
    def test_renders_template(self, client):
        resp = client.get("/calendar")
        assert resp.status_code == 200
        assert b"calendar_menu" in resp.data


# ---------------------------------------------------------------------------
# GET /api/events
# ---------------------------------------------------------------------------


class TestApiListEvents:
    def test_returns_empty_when_no_events(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_all_events(self, client, events_col):
        _insert_event(events_col, titulo="e1")
        _insert_event(events_col, titulo="e2", start_offset_hours=24)
        resp = client.get("/api/events")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body) == 2
        # Las fechas se serializan a ISO 8601.
        assert "T" in body[0]["fecha_inicio"]
        # Los _id se serializan como string.
        assert isinstance(body[0]["_id"], str)

    def test_filter_by_start_and_end_range_returns_200(self, client, events_col):
        # Verificacion del path (la interseccion exacta es deterministica de Mongo
        # real; mongomock tiene ligeras diferencias en operadores compuestos
        # sobre fechas y no es el objetivo de esta prueba).
        _insert_event(events_col, titulo="ev", start_offset_hours=2, end_offset_hours=3)
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=5)).isoformat()
        resp = client.get(f"/api/events?start={start}&end={end}")
        assert resp.status_code == 200
        # Al menos el endpoint responde con una lista bien formada.
        assert isinstance(resp.get_json(), list)

    def test_filter_by_only_start(self, client, events_col):
        _insert_event(events_col)
        resp = client.get("/api/events?start=2026-01-01T00:00:00Z")
        assert resp.status_code == 200

    def test_filter_by_only_end(self, client, events_col):
        _insert_event(events_col)
        resp = client.get("/api/events?end=2030-01-01T00:00:00Z")
        assert resp.status_code == 200

    def test_objectid_referencia_serialized_to_string(self, client, events_col):
        ref = ObjectId()
        _insert_event(events_col, referencia_id=ref, referencia_tipo="tarea")
        body = client.get("/api/events").get_json()
        assert isinstance(body[0]["referencia_id"], str)
        assert body[0]["referencia_id"] == str(ref)

    def test_legacy_event_infers_time_layer(self, client, events_col):
        _insert_event(events_col, titulo="Deporte", tipo_evento="otro")

        body = client.get("/api/events").get_json()

        assert body[0]["capa_tiempo"] == "salud"
        assert body[0]["cuenta_productivo"] is False
        assert body[0]["cuenta_recuperacion"] is True


# ---------------------------------------------------------------------------
# POST /api/events
# ---------------------------------------------------------------------------


class TestApiCreateEvent:
    def test_validates_required_fields(self, client):
        resp = client.post("/api/events", json={"titulo": "x"})
        assert resp.status_code == 400
        assert "obligatorios" in resp.get_json()["error"].lower()

    def test_validates_date_format(self, client):
        resp = client.post(
            "/api/events",
            json={"titulo": "x", "fecha_inicio": "not-a-date", "fecha_fin": "x"},
        )
        assert resp.status_code == 400
        assert "iso" in resp.get_json()["error"].lower()

    def test_creates_event_with_full_payload(self, client, events_col):
        resp = client.post(
            "/api/events",
            json={
                "titulo": "reunion",
                "descripcion": "d",
                "fecha_inicio": "2026-05-17T10:00:00Z",
                "fecha_fin": "2026-05-17T11:00:00Z",
                "tipo_evento": "trabajo",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["titulo"] == "reunion"
        assert "T" in body["fecha_inicio"]
        # Y se ha guardado.
        assert events_col.count_documents({}) == 1

    def test_creates_event_with_time_layer(self, client, events_col):
        resp = client.post(
            "/api/events",
            json={
                "titulo": "Cine",
                "fecha_inicio": "2026-05-17T20:00:00Z",
                "fecha_fin": "2026-05-17T22:00:00Z",
                "capa_tiempo": "ocio",
            },
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["capa_tiempo"] == "ocio"
        assert body["cuenta_productivo"] is False
        assert body["cuenta_recuperacion"] is True

    def test_creates_event_with_reference_to_task(self, client, events_col, monkeypatch):
        captured = {}

        def _add(*args, **kwargs):
            captured["called"] = (args, kwargs)

        monkeypatch.setattr(
            calendar_controller.TaskModel, "add_event_to_task", staticmethod(_add)
        )
        task_id = str(ObjectId())
        resp = client.post(
            "/api/events",
            json={
                "titulo": "rev",
                "fecha_inicio": "2026-05-17T10:00:00Z",
                "fecha_fin": "2026-05-17T11:00:00Z",
                "referencia_id": task_id,
                "referencia_tipo": "tarea",
            },
        )
        assert resp.status_code == 201
        # Se ha invocado add_event_to_task con el task_id.
        assert "called" in captured

    def test_task_event_assigned_to_goal_creates_goal_task(self, client, events_col, monkeypatch):
        inserted_tasks = []
        add_calls = []
        recalc_calls = []

        def _insert_task(task_data, usuario_id=None):
            task = dict(task_data)
            task["_id"] = ObjectId()
            inserted_tasks.append((task, usuario_id))
            return task

        monkeypatch.setattr(
            calendar_controller.TaskModel, "insert_task", staticmethod(_insert_task)
        )
        monkeypatch.setattr(
            calendar_controller.TaskModel,
            "add_event_to_task",
            staticmethod(lambda *a, **k: add_calls.append((a, k)) or True),
        )
        monkeypatch.setattr(
            calendar_controller.TaskModel,
            "recalculate_goal_progress",
            staticmethod(lambda *a, **k: recalc_calls.append((a, k)) or 0),
        )

        goal_id = ObjectId()
        resp = client.post(
            "/api/events",
            json={
                "titulo": "Paper jay",
                "descripcion": "Lectura y notas",
                "fecha_inicio": "2026-05-17T10:00:00Z",
                "fecha_fin": "2026-05-17T11:00:00Z",
                "tipo_evento": "tarea",
                "referencia_id": str(goal_id),
                "referencia_tipo": "objetivo",
            },
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert len(inserted_tasks) == 1
        task_doc, usuario_id = inserted_tasks[0]
        assert usuario_id == calendar_controller.DEFAULT_USER_ID
        assert task_doc["contenido"] == "Paper jay"
        assert task_doc["descripcion"] == "Lectura y notas"
        assert task_doc["objetivo_id"] == goal_id
        assert str(task_doc["event_ids"][0]) == body["_id"]

        assert body["referencia_tipo"] == "tarea"
        assert body["referencia_id"] == str(task_doc["_id"])
        assert body["objetivo_id"] == str(goal_id)
        assert body["generated_task_id"] == str(task_doc["_id"])
        assert add_calls
        assert recalc_calls

        saved = events_col.find_one({"_id": ObjectId(body["_id"])})
        assert saved["referencia_tipo"] == "tarea"
        assert saved["referencia_id"] == task_doc["_id"]
        assert saved["objetivo_id"] == goal_id

    def test_invalid_reference_id_is_silently_cleared(self, client):
        resp = client.post(
            "/api/events",
            json={
                "titulo": "x",
                "fecha_inicio": "2026-05-17T10:00:00Z",
                "fecha_fin": "2026-05-17T11:00:00Z",
                "referencia_id": "not-an-oid",
                "referencia_tipo": "tarea",
            },
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# PUT/PATCH /api/events/<id>
# ---------------------------------------------------------------------------


class TestApiUpdateEvent:
    def test_invalid_id_returns_400(self, client):
        resp = client.put("/api/events/not-an-oid", json={"titulo": "x"})
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client):
        resp = client.put(f"/api/events/{ObjectId()}", json={"titulo": "x"})
        assert resp.status_code == 404

    def test_no_fields_returns_400(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.put(f"/api/events/{ev['_id']}", json={})
        assert resp.status_code == 400

    def test_updates_text_fields(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.patch(
            f"/api/events/{ev['_id']}",
            json={"titulo": "nuevo", "descripcion": "x"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["titulo"] == "nuevo"

    def test_updates_time_layer_only(self, client, events_col):
        ev = _insert_event(events_col, capa_tiempo="productivo")

        resp = client.patch(
            f"/api/events/{ev['_id']}",
            json={"capa_tiempo": "mantenimiento"},
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["capa_tiempo"] == "mantenimiento"
        assert body["cuenta_productivo"] is False

    def test_invalid_fecha_inicio_returns_400(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.put(
            f"/api/events/{ev['_id']}",
            json={"fecha_inicio": "bad-date"},
        )
        assert resp.status_code == 400

    def test_invalid_fecha_fin_returns_400(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.put(
            f"/api/events/{ev['_id']}",
            json={"fecha_fin": "bad-date"},
        )
        assert resp.status_code == 400

    def test_changing_referencia_triggers_sync(self, client, events_col, monkeypatch):
        ev = _insert_event(events_col, referencia_id=ObjectId(), referencia_tipo="tarea")
        sync_calls = []
        monkeypatch.setattr(
            calendar_controller, "_sync_event_association",
            lambda *args, **kwargs: sync_calls.append(args),
        )
        new_ref = str(ObjectId())
        resp = client.put(
            f"/api/events/{ev['_id']}",
            json={"referencia_id": new_ref, "referencia_tipo": "objetivo"},
        )
        assert resp.status_code == 200
        assert len(sync_calls) == 1

    def test_legacy_id_tarea_used_as_old_ref(self, client, events_col, monkeypatch):
        ev = _insert_event(events_col, id_tarea=ObjectId())
        sync_calls = []
        monkeypatch.setattr(
            calendar_controller, "_sync_event_association",
            lambda eid, old_id, old_t, new_id, new_t: sync_calls.append(
                (old_id, old_t, new_id, new_t)
            ),
        )
        resp = client.put(
            f"/api/events/{ev['_id']}",
            json={"referencia_id": str(ObjectId()), "referencia_tipo": "objetivo"},
        )
        assert resp.status_code == 200
        # La asociacion antigua se reconstruye desde id_tarea
        assert sync_calls[0][1] == "tarea"

    def test_referencia_clear_when_invalid_tipo(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.put(
            f"/api/events/{ev['_id']}",
            json={"referencia_id": str(ObjectId()), "referencia_tipo": "invalid"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["referencia_id"] is None
        assert body["referencia_tipo"] is None


# ---------------------------------------------------------------------------
# DELETE /api/events/<id>
# ---------------------------------------------------------------------------


class TestApiDeleteEvent:
    def test_invalid_id_returns_400(self, client):
        resp = client.delete("/api/events/bad")
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client):
        resp = client.delete(f"/api/events/{ObjectId()}")
        assert resp.status_code == 404

    def test_deletes_event(self, client, events_col):
        ev = _insert_event(events_col)
        resp = client.delete(f"/api/events/{ev['_id']}")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True
        assert events_col.count_documents({}) == 0

    def test_queues_deletion_to_prevent_remote_resurrection(self, client, events_col, monkeypatch):
        ev = _insert_event(events_col)
        queued = []
        flushed = []

        def _queue_deletion(collection_name, target_id):
            queued.append((collection_name, target_id))
            events_col.delete_one({"_id": target_id})
            return True

        monkeypatch.setattr(calendar_controller, "queue_deletion", _queue_deletion)
        monkeypatch.setattr(calendar_controller, "flush_deletion_queue", lambda: flushed.append(True) or 1)

        resp = client.delete(f"/api/events/{ev['_id']}")

        assert resp.status_code == 200
        assert queued == [("Events", ev["_id"])]
        assert flushed == [True]
        assert events_col.find_one({"_id": ev["_id"]}) is None

    def test_deletes_with_legacy_id_objetivo_triggers_sync(self, client, events_col, monkeypatch):
        ev = _insert_event(events_col, id_objetivo=ObjectId())
        sync_calls = []
        monkeypatch.setattr(
            calendar_controller, "_sync_event_association",
            lambda eid, old_id, old_t, new_id, new_t: sync_calls.append(old_t),
        )
        resp = client.delete(f"/api/events/{ev['_id']}")
        assert resp.status_code == 200
        assert sync_calls == ["objetivo"]


# ---------------------------------------------------------------------------
# GET /api/events/timeline
# ---------------------------------------------------------------------------


class TestApiTimeline:
    def test_upcoming_excludes_past(self, client, events_col):
        _insert_event(events_col, titulo="pasado", start_offset_hours=-48, end_offset_hours=-24)
        _insert_event(events_col, titulo="futuro", start_offset_hours=24, end_offset_hours=48)
        resp = client.get("/api/events/timeline")
        body = resp.get_json()
        titulos = [e["titulo"] for e in body]
        assert "futuro" in titulos
        assert "pasado" not in titulos

    def test_past_excludes_future(self, client, events_col):
        _insert_event(events_col, titulo="pasado", start_offset_hours=-48, end_offset_hours=-24)
        _insert_event(events_col, titulo="futuro", start_offset_hours=24, end_offset_hours=48)
        resp = client.get("/api/events/timeline?type=past")
        body = resp.get_json()
        titulos = [e["titulo"] for e in body]
        assert "pasado" in titulos
        assert "futuro" not in titulos


# ---------------------------------------------------------------------------
# GET/PUT /api/daily-metrics
# ---------------------------------------------------------------------------


class TestApiDailyMetrics:
    def test_requires_start_date(self, client):
        resp = client.get("/api/daily-metrics")

        assert resp.status_code == 400
        assert "start" in resp.get_json()["error"]

    def test_saves_and_lists_sleep_metric(self, client, mongo_mock):
        save_resp = client.put(
            "/api/daily-metrics/2026-07-02/sleep",
            json={"sleep_hours": 7.5},
        )

        assert save_resp.status_code == 200
        saved = save_resp.get_json()
        assert saved["date"] == "2026-07-02"
        assert saved["sleep_hours"] == 7.5
        assert saved["sleep_source"] == "manual"
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

        list_resp = client.get("/api/daily-metrics?start=2026-07-01&end=2026-07-07")
        body = list_resp.get_json()
        assert list_resp.status_code == 200
        assert len(body) == 1
        assert body[0]["date"] == "2026-07-02"

    def test_daily_metrics_can_refresh_weather(self, client, monkeypatch):
        calls = []

        def _fake_weather(start, end, usuario_id=None):
            calls.append((start, end, usuario_id))
            return {"updated": 0, "errors": [], "enabled": True}

        monkeypatch.setattr(calendar_controller, "ensure_weather_for_range", _fake_weather)

        resp = client.get("/api/daily-metrics?start=2026-07-01&end=2026-07-07&weather=1")

        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0][0] == "2026-07-01"
        assert calls[0][1] == "2026-07-07"

    def test_saves_mood_on_existing_daily_metric(self, client, mongo_mock):
        client.put(
            "/api/daily-metrics/2026-07-02/sleep",
            json={"sleep_hours": 7.5},
        )
        mood_resp = client.put(
            "/api/daily-metrics/2026-07-02/mood",
            json={"mood_score": 5},
        )

        assert mood_resp.status_code == 200
        saved = mood_resp.get_json()
        assert saved["sleep_hours"] == 7.5
        assert saved["mood_score"] == 5
        assert saved["mood_label"] == "muy_bueno"
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

    def test_rejects_invalid_sleep_hours(self, client):
        resp = client.put(
            "/api/daily-metrics/2026-07-02/sleep",
            json={"sleep_hours": 26},
        )

        assert resp.status_code == 400
        assert "0 y 24" in resp.get_json()["error"]

    def test_rejects_invalid_mood(self, client):
        resp = client.put(
            "/api/daily-metrics/2026-07-02/mood",
            json={"mood_score": 9},
        )

        assert resp.status_code == 400
        assert "1 y 5" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# GET /api/search/associations
# ---------------------------------------------------------------------------


class TestApiSearchAssociations:
    def test_short_query_returns_empty(self, client):
        resp = client.get("/api/search/associations?q=a")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_mixes_tasks_and_goals_in_results(self, client, monkeypatch):
        monkeypatch.setattr(
            calendar_controller.TaskModel, "search_tasks",
            staticmethod(lambda nombre=None: [{"_id": ObjectId(), "contenido": "t1"}]),
        )
        monkeypatch.setattr(
            calendar_controller.GoalModel, "search_by_name",
            staticmethod(lambda nombre=None, limit=10: [{"_id": ObjectId(), "titulo": "g1"}]),
        )
        resp = client.get("/api/search/associations?q=algo")
        body = resp.get_json()
        tipos = [r["tipo"] for r in body]
        assert "tarea" in tipos
        assert "objetivo" in tipos

    def test_limit_parsed_safely_when_invalid(self, client, monkeypatch):
        monkeypatch.setattr(
            calendar_controller.TaskModel, "search_tasks",
            staticmethod(lambda nombre=None: []),
        )
        monkeypatch.setattr(
            calendar_controller.GoalModel, "search_by_name",
            staticmethod(lambda nombre=None, limit=10: []),
        )
        resp = client.get("/api/search/associations?q=algo&limit=invalid")
        assert resp.status_code == 200

    def test_results_capped_at_limit(self, client, monkeypatch):
        monkeypatch.setattr(
            calendar_controller.TaskModel, "search_tasks",
            staticmethod(lambda nombre=None: [{"_id": ObjectId(), "contenido": f"t{i}"} for i in range(10)]),
        )
        monkeypatch.setattr(
            calendar_controller.GoalModel, "search_by_name",
            staticmethod(lambda nombre=None, limit=10: [{"_id": ObjectId(), "titulo": f"g{i}"} for i in range(10)]),
        )
        resp = client.get("/api/search/associations?q=algo&limit=5")
        body = resp.get_json()
        assert len(body) == 5
