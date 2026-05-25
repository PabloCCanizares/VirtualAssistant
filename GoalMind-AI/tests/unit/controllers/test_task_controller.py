"""Bateria completa del controlador REST de tareas (`controllers/task_controller.py`).

Patron: cliente de pruebas de Flask + monkeypatch sobre los metodos estaticos de
los modelos (`TaskModel`, `GoalModel`, `ProjectModel`, `CategoryModel`) para
evitar tocar MongoDB. `render_template` se sustituye por una funcion que
devuelve una marca legible con los argumentos clave, lo que permite verificar
que el controlador construye el contexto correcto sin necesidad de los ficheros
de plantilla.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId
from flask import Flask

from controllers import task_controller
from controllers.task_controller import task_bp


@pytest.fixture
def client(monkeypatch):
    """Cliente Flask con `task_bp` registrado y `render_template` mockeado."""
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    def _fake_render(template_name, **ctx):
        # Devuelve marca legible para poder inspeccionar el contexto en los asserts.
        keys = ",".join(sorted(ctx.keys()))
        return f"RENDER::{template_name}::{keys}"

    monkeypatch.setattr(task_controller, "render_template", _fake_render)
    app.register_blueprint(task_bp)
    return app.test_client()


def _stub_context_loaders(monkeypatch, goals=None, projects=None, categories=None):
    """Stub de los modelos auxiliares que cargan contexto comun para los listados."""
    monkeypatch.setattr(
        task_controller.GoalModel,
        "get_all_goals",
        staticmethod(lambda usuario_id=None: goals or []),
    )
    monkeypatch.setattr(
        task_controller.ProjectModel,
        "get_all_projects",
        staticmethod(lambda usuario_id=None: projects or []),
    )
    monkeypatch.setattr(
        task_controller.CategoryModel,
        "get_all_categories",
        staticmethod(lambda usuario_id=None: categories or []),
    )


def _task_doc(contenido="hacer cosa", objetivo_id=None, categorias=None, event_ids=None):
    doc = {
        "_id": ObjectId(),
        "contenido": contenido,
        "estado": "pendiente",
        "prioridad": "media",
    }
    if objetivo_id is not None:
        doc["objetivo_id"] = objetivo_id
    if categorias is not None:
        doc["categorias"] = categorias
    if event_ids is not None:
        doc["event_ids"] = event_ids
    return doc


# ---------------------------------------------------------------------------
# GET /tasks/
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_renders_with_tasks_and_context(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_all_tasks",
            staticmethod(lambda usuario_id=None: [_task_doc()]),
        )
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        assert b"RENDER::" in resp.data
        # Las claves esperadas en el contexto:
        for key in (b"tasks", b"goals", b"goal_titles", b"categories", b"category_names", b"page"):
            assert key in resp.data

    def test_renders_when_no_tasks(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_all_tasks",
            staticmethod(lambda usuario_id=None: []),
        )
        resp = client.get("/tasks/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /tasks/<task_id>
# ---------------------------------------------------------------------------


class TestViewTask:
    def test_redirects_when_task_not_found(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_task_by_id",
            staticmethod(lambda tid, usuario_id=None: None),
        )
        resp = client.get("/tasks/abc")
        # redirect a list_tasks
        assert resp.status_code == 302
        assert "/tasks/" in resp.headers["Location"]

    def test_renders_task_detail(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        task = _task_doc(contenido="t1")
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_task_by_id",
            staticmethod(lambda tid, usuario_id=None: task),
        )
        resp = client.get(f"/tasks/{task['_id']}")
        assert resp.status_code == 200
        assert b"selected_task" in resp.data

    def test_handles_model_exception(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)

        def _boom(tid, usuario_id=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(task_controller.TaskModel, "get_task_by_id", staticmethod(_boom))
        resp = client.get("/tasks/abc")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /tasks/user[/<user_id>]
# ---------------------------------------------------------------------------


class TestListTasksByUser:
    def test_uses_default_user_when_id_zero(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        captured = {}

        def _get(user_id):
            captured["uid"] = user_id
            return []

        monkeypatch.setattr(task_controller.TaskModel, "get_task_by_user", staticmethod(_get))
        resp = client.get("/tasks/user/0")
        assert resp.status_code == 200
        assert captured["uid"] == task_controller.DEFAULT_USER_ID

    def test_explicit_user_propagates(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        captured = {}

        def _get(user_id):
            captured["uid"] = user_id
            return [_task_doc()]

        monkeypatch.setattr(task_controller.TaskModel, "get_task_by_user", staticmethod(_get))
        resp = client.get("/tasks/user/u_42")
        assert resp.status_code == 200
        assert captured["uid"] == "u_42"

    def test_no_user_param_defaults(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_task_by_user",
            staticmethod(lambda uid: []),
        )
        resp = client.get("/tasks/user")
        assert resp.status_code == 200

    def test_handles_exception_redirects(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)

        def _boom(uid):
            raise RuntimeError("db")

        monkeypatch.setattr(task_controller.TaskModel, "get_task_by_user", staticmethod(_boom))
        resp = client.get("/tasks/user/x")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /tasks/add
# ---------------------------------------------------------------------------


class TestAddTask:
    def test_redirects_when_no_goal_id(self, client):
        resp = client.post("/tasks/add", data={"contenido": "x"})
        # sin objetivo_id -> flash warning + redirect
        assert resp.status_code == 302

    def test_inserts_when_goal_id_present(self, client, monkeypatch):
        captured = {}

        def _insert(data):
            captured["data"] = data
            data["_id"] = ObjectId()
            return data

        monkeypatch.setattr(task_controller.TaskModel, "insert_task", staticmethod(_insert))
        goal_oid = ObjectId()
        cat_oid = ObjectId()
        resp = client.post(
            "/tasks/add",
            data={
                "objetivo_id": str(goal_oid),
                "contenido": "redactar intro",
                "descripcion": "primer borrador",
                "fecha_limite": "2026-06-01",
                "estado": "pendiente",
                "prioridad": "alta",
                "categorias": f"{cat_oid},",  # CSV separado por comas
            },
        )
        assert resp.status_code == 302
        # La tarea se inserto con los datos esperados.
        d = captured["data"]
        assert d["contenido"] == "redactar intro"
        assert d["prioridad"] == "alta"
        assert isinstance(d["objetivo_id"], ObjectId)
        assert d["categorias"] == [cat_oid]

    def test_ignores_invalid_category_ids(self, client, monkeypatch):
        captured = {}

        def _insert(data):
            captured["data"] = data
            return data

        monkeypatch.setattr(task_controller.TaskModel, "insert_task", staticmethod(_insert))
        resp = client.post(
            "/tasks/add",
            data={
                "objetivo_id": str(ObjectId()),
                "contenido": "x",
                "categorias": "not-a-valid-oid,also-bad",
            },
        )
        assert resp.status_code == 302
        # Las categorias invalidas se filtran silenciosamente.
        assert captured["data"]["categorias"] == []

    def test_uses_defaults_for_missing_optional_fields(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "insert_task",
            staticmethod(lambda d: captured.setdefault("data", d) or d),
        )
        resp = client.post("/tasks/add", data={"objetivo_id": str(ObjectId()), "contenido": "x"})
        assert resp.status_code == 302
        assert captured["data"]["estado"] == "pendiente"
        assert captured["data"]["prioridad"] == "media"

    def test_insert_exception_redirects_gracefully(self, client, monkeypatch):
        def _boom(d):
            raise RuntimeError("fail")

        monkeypatch.setattr(task_controller.TaskModel, "insert_task", staticmethod(_boom))
        resp = client.post(
            "/tasks/add",
            data={"objetivo_id": str(ObjectId()), "contenido": "x"},
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /tasks/update/<task_id>
# ---------------------------------------------------------------------------


class TestUpdateTask:
    def test_update_passes_fields_to_model(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "update_task",
            staticmethod(lambda tid, upd, usuario_id=None: captured.update({"tid": tid, "upd": upd})),
        )
        tid = str(ObjectId())
        resp = client.post(
            f"/tasks/update/{tid}",
            data={"contenido": "nuevo", "estado": "completada", "prioridad": "alta"},
        )
        assert resp.status_code == 302
        assert captured["tid"] == tid
        assert captured["upd"]["contenido"] == "nuevo"
        assert captured["upd"]["estado"] == "completada"

    def test_update_filters_empty_values(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "update_task",
            staticmethod(lambda tid, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(
            f"/tasks/update/{ObjectId()}",
            data={"contenido": "algo", "descripcion": ""},
        )
        assert resp.status_code == 302
        # Los campos con valor vacio se filtran
        assert "descripcion" not in captured["upd"]

    def test_update_with_categorias_converts_to_oid(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "update_task",
            staticmethod(lambda tid, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        cat_oid = ObjectId()
        resp = client.post(
            f"/tasks/update/{ObjectId()}",
            data={"contenido": "x", "categorias": str(cat_oid)},
        )
        assert resp.status_code == 302
        assert captured["upd"]["categorias"] == [cat_oid]

    def test_update_with_objetivo_id_converts_to_oid(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "update_task",
            staticmethod(lambda tid, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        goal_oid = ObjectId()
        resp = client.post(
            f"/tasks/update/{ObjectId()}",
            data={"contenido": "x", "objetivo_id": str(goal_oid)},
        )
        assert resp.status_code == 302
        assert captured["upd"]["objetivo_id"] == goal_oid

    def test_update_exception_redirects(self, client, monkeypatch):
        def _boom(tid, upd, usuario_id=None):
            raise RuntimeError("fail")

        monkeypatch.setattr(task_controller.TaskModel, "update_task", staticmethod(_boom))
        resp = client.post(f"/tasks/update/{ObjectId()}", data={"contenido": "x"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /tasks/delete/<task_id>
# ---------------------------------------------------------------------------


class TestDeleteTask:
    def test_delete_invokes_model(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "delete_task",
            staticmethod(lambda tid, usuario_id=None: captured.update({"tid": tid}) or True),
        )
        tid = str(ObjectId())
        resp = client.post(f"/tasks/delete/{tid}")
        assert resp.status_code == 302
        assert captured["tid"] == tid

    def test_delete_exception_redirects(self, client, monkeypatch):
        def _boom(tid, usuario_id=None):
            raise RuntimeError("db")

        monkeypatch.setattr(task_controller.TaskModel, "delete_task", staticmethod(_boom))
        resp = client.post(f"/tasks/delete/{ObjectId()}")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /tasks/filter
# ---------------------------------------------------------------------------


class TestFilter:
    def test_filter_by_nombre(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        captured = {}

        def _search(nombre=None, categoria=None, category_ids=None, usuario_id=None):
            captured["nombre"] = nombre
            captured["cats"] = category_ids
            return [_task_doc()]

        monkeypatch.setattr(task_controller.TaskModel, "search_tasks", staticmethod(_search))
        resp = client.get("/tasks/filter?nombre=urgente")
        assert resp.status_code == 200
        assert captured["nombre"] == "urgente"
        assert captured["cats"] is None

    def test_filter_by_categories_csv(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        captured = {}
        monkeypatch.setattr(
            task_controller.TaskModel,
            "search_tasks",
            staticmethod(
                lambda nombre=None, categoria=None, category_ids=None, usuario_id=None: captured.update(
                    {"cats": category_ids}
                )
                or []
            ),
        )
        resp = client.get("/tasks/filter?categoria=id1,id2&categoria=id3")
        assert resp.status_code == 200
        assert captured["cats"] == ["id1", "id2", "id3"]


# ---------------------------------------------------------------------------
# GET /tasks/search
# ---------------------------------------------------------------------------


class TestSearchById:
    def test_search_with_id_returns_task(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        task = _task_doc()
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_task_by_id",
            staticmethod(lambda tid, usuario_id=None: task),
        )
        resp = client.get(f"/tasks/search?id={task['_id']}")
        assert resp.status_code == 200
        assert b"page" in resp.data

    def test_search_with_invalid_id_flashes(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)

        def _boom(tid, usuario_id=None):
            raise ValueError("bad id")

        monkeypatch.setattr(task_controller.TaskModel, "get_task_by_id", staticmethod(_boom))
        resp = client.get("/tasks/search?id=xxx")
        assert resp.status_code == 200  # render con tasks=[]

    def test_search_empty_id_renders_empty(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        resp = client.get("/tasks/search")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /tasks/bulk-delete
# ---------------------------------------------------------------------------


class TestBulkDelete:
    def test_bulk_delete_via_json(self, client, monkeypatch):
        ids = [str(ObjectId()), str(ObjectId())]
        captured = {}

        def _delete(id_list, usuario_id=None):
            captured["ids"] = id_list
            return len(id_list)

        monkeypatch.setattr(
            task_controller.TaskModel, "delete_tasks_by_ids", staticmethod(_delete)
        )
        resp = client.post("/tasks/bulk-delete", json={"selected_tasks": ids})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["deleted_count"] == 2
        assert captured["ids"] == ids

    def test_bulk_delete_empty_json_returns_400(self, client):
        resp = client.post("/tasks/bulk-delete", json={"selected_tasks": []})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_bulk_delete_via_form_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            task_controller.TaskModel,
            "delete_tasks_by_ids",
            staticmethod(lambda ids, usuario_id=None: len(ids)),
        )
        resp = client.post(
            "/tasks/bulk-delete",
            data={"selected_tasks": [str(ObjectId()), str(ObjectId())]},
        )
        assert resp.status_code == 302

    def test_bulk_delete_exception_via_json_returns_500(self, client, monkeypatch):
        def _boom(ids, usuario_id=None):
            raise RuntimeError("db")

        monkeypatch.setattr(
            task_controller.TaskModel, "delete_tasks_by_ids", staticmethod(_boom)
        )
        resp = client.post("/tasks/bulk-delete", json={"selected_tasks": [str(ObjectId())]})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /tasks/bulk-assign-goal
# ---------------------------------------------------------------------------


class TestBulkAssignGoal:
    def test_assigns_goal_to_selected_tasks(self, client, monkeypatch):
        goal_id = str(ObjectId())
        task_ids = [str(ObjectId()), str(ObjectId())]
        monkeypatch.setattr(
            task_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: {"_id": ObjectId(gid), "titulo": "G"}),
        )
        monkeypatch.setattr(
            task_controller.TaskModel,
            "assign_goal_to_tasks",
            staticmethod(lambda tids, gid, usuario_id=None: len(tids)),
        )
        resp = client.post(
            "/tasks/bulk-assign-goal",
            json={"selected_tasks": task_ids, "objetivo_id": goal_id},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["updated_count"] == 2

    def test_empty_payload_returns_400(self, client):
        # JSON valido pero vacio: el controlador lo rechaza con 400.
        resp = client.post("/tasks/bulk-assign-goal", json={})
        assert resp.status_code == 400

    def test_no_tasks_returns_400(self, client):
        resp = client.post(
            "/tasks/bulk-assign-goal",
            json={"selected_tasks": [], "objetivo_id": str(ObjectId())},
        )
        assert resp.status_code == 400

    def test_no_goal_returns_400(self, client):
        resp = client.post(
            "/tasks/bulk-assign-goal",
            json={"selected_tasks": [str(ObjectId())]},
        )
        assert resp.status_code == 400

    def test_unknown_goal_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            task_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: None),
        )
        resp = client.post(
            "/tasks/bulk-assign-goal",
            json={"selected_tasks": [str(ObjectId())], "objetivo_id": str(ObjectId())},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /tasks/api/by-date-range
# ---------------------------------------------------------------------------


class TestByDateRange:
    def test_groups_tasks_by_date_in_range(self, client, monkeypatch):
        tasks = [
            {"contenido": "t1", "fecha_limite": datetime(2026, 5, 17), "estado": "pendiente", "prioridad": "alta"},
            {"contenido": "t2", "fecha_limite": "2026-05-18T09:00:00", "estado": "pendiente", "prioridad": "media"},
            {"contenido": "t3", "fecha_limite": datetime(2026, 6, 1), "estado": "pendiente"},  # fuera de rango
            {"contenido": "sin_fecha"},  # se ignora
        ]
        monkeypatch.setattr(
            task_controller.TaskModel,
            "get_all_tasks",
            staticmethod(lambda usuario_id=None: tasks),
        )
        resp = client.get("/tasks/api/by-date-range?start=2026-05-15&end=2026-05-31")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "2026-05-17" in body
        assert "2026-05-18" in body
        assert "2026-06-01" not in body
        assert body["2026-05-17"][0]["titulo"] == "t1"

    def test_missing_params_returns_empty(self, client):
        resp = client.get("/tasks/api/by-date-range")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_exception_returns_empty(self, client, monkeypatch):
        def _boom(usuario_id=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(task_controller.TaskModel, "get_all_tasks", staticmethod(_boom))
        resp = client.get("/tasks/api/by-date-range?start=2026-01-01&end=2026-12-31")
        assert resp.status_code == 200
        assert resp.get_json() == {}
