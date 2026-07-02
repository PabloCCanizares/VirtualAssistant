"""Bateria completa del controlador REST de objetivos (`controllers/goal_controller.py`).

Patron: cliente de Flask + monkeypatch sobre `GoalModel`, `ProjectModel`,
`TaskModel`, `CategoryModel`, `queue_deletion` y `flush_deletion_queue`. Se
registra ademas un blueprint *stub* para `project_bp` (al que el controlador
redirige tras crear / borrar un objetivo) para que `url_for` no falle.
`render_template` se sustituye por un renderizador trivial que devuelve el
nombre de plantilla y las claves del contexto.
"""

from __future__ import annotations

import pytest
from bson import ObjectId
from flask import Blueprint, Flask

from controllers import goal_controller
from controllers.goal_controller import goal_bp


def _stub_project_bp() -> Blueprint:
    bp = Blueprint("project_bp", __name__, url_prefix="/projects")
    bp.add_url_rule("/", endpoint="list_projects", view_func=lambda: "list")
    bp.add_url_rule("/<project_id>", endpoint="view_project", view_func=lambda project_id: "view")
    return bp


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    def _fake_render(template_name, **ctx):
        keys = ",".join(sorted(ctx.keys()))
        return f"RENDER::{template_name}::{keys}"

    monkeypatch.setattr(goal_controller, "render_template", _fake_render)
    # queue_deletion y flush_deletion_queue no deben tocar Mongo real.
    monkeypatch.setattr(goal_controller, "queue_deletion", lambda *a, **k: True)
    monkeypatch.setattr(goal_controller, "flush_deletion_queue", lambda: 0)

    app.register_blueprint(_stub_project_bp())
    app.register_blueprint(goal_bp)
    return app.test_client()


def _stub_context_loaders(monkeypatch, projects=None, categories=None):
    monkeypatch.setattr(
        goal_controller.ProjectModel,
        "get_all_projects",
        staticmethod(lambda usuario_id=None: projects or []),
    )
    monkeypatch.setattr(
        goal_controller.CategoryModel,
        "get_all_categories",
        staticmethod(lambda usuario_id=None: categories or []),
    )


def _goal_doc(titulo="redactar", project_id=None):
    return {
        "_id": ObjectId(),
        "titulo": titulo,
        "project_id": project_id or ObjectId(),
        "progreso": 0,
        "estado": "En progreso",
    }


# ---------------------------------------------------------------------------
# POST /goals/add
# ---------------------------------------------------------------------------


class TestAddGoal:
    def test_redirects_when_no_project_id(self, client):
        resp = client.post("/goals/add", data={"titulo": "x"})
        assert resp.status_code == 302
        assert "/projects/" in resp.headers["Location"]

    def test_inserts_with_full_payload(self, client, monkeypatch):
        captured = {}

        def _insert(d):
            captured["data"] = d
            d["_id"] = ObjectId()
            return d

        monkeypatch.setattr(goal_controller.GoalModel, "insert_goal", staticmethod(_insert))
        cat = ObjectId()
        pid = str(ObjectId())
        resp = client.post(
            "/goals/add",
            data={
                "project_id": pid,
                "titulo": "obj1",
                "descripcion": "d",
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
                "categorias": str(cat),
                "progreso": "30",
                "estado": "En progreso",
                "prioridad": "Alta",
            },
        )
        assert resp.status_code == 302
        d = captured["data"]
        assert d["titulo"] == "obj1"
        assert d["progreso"] == 30
        assert d["categorias"] == [cat]

    def test_progress_defaults_to_zero(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "insert_goal",
            staticmethod(lambda d: captured.setdefault("d", d) or d),
        )
        resp = client.post("/goals/add", data={"project_id": str(ObjectId()), "titulo": "g"})
        assert resp.status_code == 302
        assert captured["d"]["progreso"] == 0
        assert captured["d"]["estado"] == "En progreso"

    def test_insert_exception_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "insert_goal",
            staticmethod(lambda d: (_ for _ in ()).throw(RuntimeError("fail"))),
        )
        resp = client.post("/goals/add", data={"project_id": str(ObjectId()), "titulo": "x"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /goals/<goal_id>
# ---------------------------------------------------------------------------


class TestViewGoal:
    def test_redirects_when_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: None),
        )
        resp = client.get(f"/goals/{ObjectId()}")
        assert resp.status_code == 302

    def test_renders_with_tasks_and_context(self, client, monkeypatch):
        _stub_context_loaders(monkeypatch)
        goal = _goal_doc()
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "get_tasks_by_goal",
            staticmethod(
                lambda gid, usuario_id=None: [
                    {"_id": ObjectId(), "contenido": "t1", "objetivo_id": goal["_id"]},
                ]
            ),
        )
        resp = client.get(f"/goals/{goal['_id']}")
        assert resp.status_code == 200
        assert b"goal" in resp.data
        assert b"tasks" in resp.data

    def test_handles_exception(self, client, monkeypatch):
        def _boom(gid, usuario_id=None):
            raise RuntimeError("db")

        monkeypatch.setattr(goal_controller.GoalModel, "get_goal_by_id", staticmethod(_boom))
        resp = client.get(f"/goals/{ObjectId()}")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /goals/<goal_id>/notes/*
# ---------------------------------------------------------------------------


class TestGoalNotes:
    def test_add_goal_note_appends_note(self, client, monkeypatch):
        gid = str(ObjectId())
        goal = {"_id": ObjectId(gid), "notas": []}
        captured = {}

        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda goal_id, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(
                lambda goal_id, updates, usuario_id=None: captured.update(
                    {"goal_id": goal_id, "updates": updates}
                )
            ),
        )

        resp = client.post(f"/goals/{gid}/notes/add", data={"note_text": "Idea clave"})

        assert resp.status_code == 302
        assert captured["goal_id"] == gid
        assert len(captured["updates"]["notas"]) == 1
        assert captured["updates"]["notas"][0]["text"] == "Idea clave"
        assert "_id" in captured["updates"]["notas"][0]
        assert "created_at" in captured["updates"]["notas"][0]

    def test_add_goal_note_ignores_empty_text(self, client, monkeypatch):
        called = {"update": False}
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda *args, **kwargs: called.update({"update": True})),
        )

        resp = client.post(f"/goals/{ObjectId()}/notes/add", data={"note_text": "   "})

        assert resp.status_code == 302
        assert called["update"] is False

    def test_delete_goal_note_removes_matching_note(self, client, monkeypatch):
        gid = str(ObjectId())
        goal = {
            "_id": ObjectId(gid),
            "notas": [
                {"_id": "n1", "text": "quitar"},
                {"_id": "n2", "text": "mantener"},
            ],
        }
        captured = {}

        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda goal_id, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(
                lambda goal_id, updates, usuario_id=None: captured.update(
                    {"goal_id": goal_id, "updates": updates}
                )
            ),
        )

        resp = client.post(f"/goals/{gid}/notes/n1/delete")

        assert resp.status_code == 302
        assert captured["goal_id"] == gid
        assert [note["_id"] for note in captured["updates"]["notas"]] == ["n2"]


# ---------------------------------------------------------------------------
# POST /goals/<goal_id>
# ---------------------------------------------------------------------------


class TestUpdateGoal:
    def test_update_passes_fields(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(
                lambda gid, upd, usuario_id=None: captured.update({"gid": gid, "upd": upd})
            ),
        )
        gid = str(ObjectId())
        resp = client.post(
            f"/goals/{gid}",
            data={"titulo": "nuevo", "estado": "Completado", "progreso": "75"},
        )
        assert resp.status_code == 302
        assert captured["gid"] == gid
        assert captured["upd"]["titulo"] == "nuevo"
        assert captured["upd"]["progreso"] == 75

    def test_invalid_progreso_is_silently_ignored(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda gid, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(
            f"/goals/{ObjectId()}",
            data={"titulo": "x", "progreso": "no-es-numero"},
        )
        assert resp.status_code == 302
        assert "progreso" not in captured["upd"]

    def test_redirect_to_param_is_used_when_safe(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda gid, upd, usuario_id=None: None),
        )
        resp = client.post(
            f"/goals/{ObjectId()}",
            data={"titulo": "x", "redirect_to": "/projects/abc"},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/projects/abc")

    def test_redirect_to_unsafe_value_is_ignored(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda gid, upd, usuario_id=None: None),
        )
        gid = str(ObjectId())
        resp = client.post(
            f"/goals/{gid}",
            data={"titulo": "x", "redirect_to": "javascript:alert(1)"},
        )
        # Cae al redirect por defecto: view_goal del propio goal.
        assert resp.status_code == 302
        assert gid in resp.headers["Location"]

    def test_update_exception_redirects(self, client, monkeypatch):
        def _boom(gid, upd, usuario_id=None):
            raise RuntimeError("fail")

        monkeypatch.setattr(goal_controller.GoalModel, "update_goal", staticmethod(_boom))
        resp = client.post(f"/goals/{ObjectId()}", data={"titulo": "x"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /goals/delete/<goal_id>  (con cascada de tareas)
# ---------------------------------------------------------------------------


class TestDeleteGoal:
    def test_delete_with_tasks_triggers_cascade(self, client, monkeypatch):
        goal = _goal_doc()
        task_ids = [ObjectId(), ObjectId()]
        queue_calls = []

        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "get_tasks_by_goal",
            staticmethod(
                lambda gid, usuario_id=None: [{"_id": tid} for tid in task_ids]
            ),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "delete_tasks_by_ids",
            staticmethod(lambda ids, usuario_id=None: len(ids)),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "delete_goal",
            staticmethod(lambda gid, usuario_id=None: True),
        )
        # Capturamos cada queue_deletion para verificar la cascada.
        monkeypatch.setattr(
            goal_controller, "queue_deletion",
            lambda col, tid: queue_calls.append((col, tid)),
        )

        resp = client.post(f"/goals/delete/{goal['_id']}")
        assert resp.status_code == 302
        # Se encolan dos tareas + un objetivo.
        cols = [c for c, _ in queue_calls]
        assert cols.count("Tasks") == 2
        assert cols.count("Goals") == 1
        # Redirige a la vista del proyecto.
        assert "/projects/" in resp.headers["Location"]

    def test_delete_without_tasks(self, client, monkeypatch):
        goal = _goal_doc()
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "get_tasks_by_goal",
            staticmethod(lambda gid, usuario_id=None: []),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "delete_goal",
            staticmethod(lambda gid, usuario_id=None: True),
        )
        resp = client.post(f"/goals/delete/{goal['_id']}")
        assert resp.status_code == 302

    def test_delete_when_model_returns_false(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: None),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "get_tasks_by_goal",
            staticmethod(lambda gid, usuario_id=None: []),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "delete_goal",
            staticmethod(lambda gid, usuario_id=None: False),
        )
        resp = client.post(f"/goals/delete/{ObjectId()}")
        # No goal → no project_id → redirect a list_projects
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/projects/")

    def test_delete_redirect_to_param_is_used(self, client, monkeypatch):
        goal = _goal_doc()
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: goal),
        )
        monkeypatch.setattr(
            goal_controller.TaskModel,
            "get_tasks_by_goal",
            staticmethod(lambda gid, usuario_id=None: []),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "delete_goal",
            staticmethod(lambda gid, usuario_id=None: True),
        )
        resp = client.post(
            f"/goals/delete/{goal['_id']}",
            data={"redirect_to": "/projects/xyz"},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/projects/xyz")

    def test_delete_outer_exception_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda gid, usuario_id=None: _goal_doc()),
        )

        def _boom(gid, usuario_id=None):
            raise RuntimeError("fail")

        monkeypatch.setattr(goal_controller.TaskModel, "get_tasks_by_goal", staticmethod(_boom))
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "delete_goal",
            staticmethod(lambda gid, usuario_id=None: (_ for _ in ()).throw(RuntimeError("x"))),
        )
        resp = client.post(f"/goals/delete/{ObjectId()}")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# PUT/PATCH /goals/api/<goal_id>
# ---------------------------------------------------------------------------


class TestApiUpdateGoal:
    def test_no_fields_returns_400(self, client):
        resp = client.put(f"/goals/api/{ObjectId()}", json={})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_updates_text_fields_via_put(self, client, monkeypatch):
        captured = {}
        gid = str(ObjectId())
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda g, u: captured.update({"upd": u})),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda g: {"_id": ObjectId(g), "titulo": "nuevo", "project_id": ObjectId()}),
        )
        resp = client.put(
            f"/goals/api/{gid}",
            json={"titulo": "nuevo", "estado": "Completado"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert captured["upd"]["titulo"] == "nuevo"

    def test_categorias_as_list(self, client, monkeypatch):
        captured = {}
        cat1 = str(ObjectId())
        cat2 = str(ObjectId())
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda g, u: captured.update({"upd": u})),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda g: {"_id": ObjectId(g), "categorias": [ObjectId(cat1), ObjectId(cat2)]}),
        )
        resp = client.put(
            f"/goals/api/{ObjectId()}",
            json={"categorias": [cat1, cat2, "invalido"]},
        )
        assert resp.status_code == 200
        # Solo las 2 validas se aceptan.
        assert len(captured["upd"]["categorias"]) == 2

    def test_categorias_as_csv_string(self, client, monkeypatch):
        captured = {}
        cat1 = str(ObjectId())
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda g, u: captured.update({"upd": u})),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda g: {"_id": ObjectId(g)}),
        )
        resp = client.patch(
            f"/goals/api/{ObjectId()}",
            json={"categorias": f"{cat1},invalido"},
        )
        assert resp.status_code == 200
        assert len(captured["upd"]["categorias"]) == 1

    def test_progreso_field(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "update_goal",
            staticmethod(lambda g, u: captured.update({"upd": u})),
        )
        monkeypatch.setattr(
            goal_controller.GoalModel,
            "get_goal_by_id",
            staticmethod(lambda g: {"_id": ObjectId(g)}),
        )
        resp = client.put(f"/goals/api/{ObjectId()}", json={"progreso": "65"})
        assert resp.status_code == 200
        assert captured["upd"]["progreso"] == 65

    def test_api_exception_returns_500(self, client, monkeypatch):
        def _boom(g, u):
            raise RuntimeError("db")

        monkeypatch.setattr(goal_controller.GoalModel, "update_goal", staticmethod(_boom))
        resp = client.put(f"/goals/api/{ObjectId()}", json={"titulo": "x"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False
