"""Bateria del nodo `action_executor_node` y sus helpers.

Cada test invoca `action_executor_node(state, _llm)` con un `state`
preparado al efecto. Los modelos acceden a `mongomock` via la fixture
compartida `mongo_mock`.
"""

from __future__ import annotations

import json

import pytest
from bson import ObjectId

from ai.agents import action_executor
from ai.agents.action_executor import (
    _build_update_fields,
    _delete_goal_cascade,
    _delete_project_cascade,
    _ensure_user_id,
    _load_context,
    _parse_object_id,
    _resolve_event_id,
    _resolve_goal_id,
    _resolve_project_id,
    _resolve_task_id,
    _safe_int,
    action_executor_node,
)

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _state(action_name, parameters=None, context=None, **extra):
    return {
        "user_id": USER_ID,
        "pending_action_intent": {"action_name": action_name, "parameters": parameters or {}},
        "action_confirmed": True,
        "context_json": json.dumps(context or {}),
        **extra,
    }


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


class TestPureHelpers:
    def test_safe_int_with_valid(self):
        assert _safe_int("42") == 42

    def test_safe_int_with_invalid_returns_default(self):
        assert _safe_int("no-numero", default=7) == 7

    def test_parse_object_id_valid(self):
        oid = ObjectId()
        assert _parse_object_id(str(oid)) == oid

    def test_parse_object_id_invalid_returns_none(self):
        assert _parse_object_id("bad-id") is None

    def test_parse_object_id_none(self):
        assert _parse_object_id(None) is None

    def test_load_context_invalid_json(self):
        assert _load_context({"context_json": "not json"}) == {}

    def test_load_context_empty(self):
        assert _load_context({}) == {}

    def test_build_update_fields_filters_none(self):
        out = _build_update_fields({"a": 1, "b": None, "c": "x"}, {"a", "b", "c"})
        assert out == {"a": 1, "c": "x"}

    def test_build_update_fields_filters_unknown(self):
        out = _build_update_fields({"a": 1, "z": 2}, {"a"})
        assert out == {"a": 1}

    def test_ensure_user_id_uses_state(self):
        assert _ensure_user_id({"user_id": "u-1"}) == "u-1"

    def test_ensure_user_id_falls_back(self, monkeypatch):
        # Sin user_id en state, usa get_app_user_id (fallback)
        assert _ensure_user_id({}) is not None


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


class TestResolvers:
    def test_resolve_project_id_direct(self):
        pid = str(ObjectId())
        out, clar = _resolve_project_id({"project_id": pid}, {})
        assert out == pid
        assert clar is None

    def test_resolve_project_id_by_title(self):
        context = {"projects": [{"_id": ObjectId(), "titulo": "TFG"}]}
        out, clar = _resolve_project_id({"titulo": "tfg"}, context)
        assert out is not None
        assert clar is None

    def test_resolve_project_id_ambiguous(self):
        context = {"projects": [
            {"_id": ObjectId(), "titulo": "TFG"},
            {"_id": ObjectId(), "titulo": "TFG-2"},
        ]}
        # "tfg" matches both
        out, clar = _resolve_project_id({"titulo": "tfg"}, context)
        assert out is None
        assert clar is not None

    def test_resolve_project_id_not_found(self):
        out, clar = _resolve_project_id({"titulo": "inexistente"}, {"projects": []})
        assert out is None
        assert clar is not None

    def test_resolve_goal_id_by_title(self):
        context = {"goals": [{"_id": ObjectId(), "titulo": "g1"}]}
        out, clar = _resolve_goal_id({"titulo": "g1"}, context)
        assert out is not None

    def test_resolve_task_id_by_content(self):
        context = {"tasks": [{"_id": ObjectId(), "contenido": "intro"}]}
        out, clar = _resolve_task_id({"contenido": "intro"}, context)
        assert out is not None

    def test_resolve_event_id_by_title(self):
        context = {"events": [{"_id": ObjectId(), "titulo": "ev1"}]}
        out, clar = _resolve_event_id({"titulo": "ev1"}, context)
        assert out is not None


# ---------------------------------------------------------------------------
# action_executor_node — cada operacion CRUD
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_creates_when_titulo_given(self, mongo_mock):
        out = action_executor_node(_state("create_project", {"titulo": "P"}), None)
        assert "Proyecto creado" in out["final_response"]
        assert mongo_mock.local_db["Projects"].count_documents({"titulo": "P"}) == 1

    def test_requires_titulo(self):
        out = action_executor_node(_state("create_project", {}), None)
        assert "Necesito el titulo" in out["final_response"]


class TestCreateGoal:
    def test_creates_with_project_id(self, mongo_mock):
        pid = ObjectId()
        out = action_executor_node(
            _state("create_goal", {"titulo": "G", "project_id": str(pid)}), None
        )
        assert "Objetivo creado" in out["final_response"]

    def test_requires_titulo(self):
        out = action_executor_node(_state("create_goal", {}), None)
        assert "Necesito el titulo" in out["final_response"]

    def test_clarification_when_project_ambiguous(self):
        out = action_executor_node(
            _state("create_goal", {"titulo": "G"}, context={"projects": []}),
            None,
        )
        assert "?" in out["final_response"]


class TestCreateTask:
    def test_creates_with_goal_id(self, mongo_mock):
        gid = ObjectId()
        out = action_executor_node(
            _state("create_task", {"contenido": "T", "goal_id": str(gid)}), None
        )
        assert "Tarea creada" in out["final_response"]

    def test_requires_contenido(self):
        out = action_executor_node(_state("create_task", {}), None)
        assert "Necesito el contenido" in out["final_response"]


class TestCreateEvent:
    def test_creates_with_required(self, mongo_mock):
        out = action_executor_node(
            _state("create_event", {"titulo": "E", "fecha_inicio": "2026-05-17T10:00"}),
            None,
        )
        assert "Evento creado" in out["final_response"]

    def test_requires_titulo(self):
        out = action_executor_node(_state("create_event", {}), None)
        assert "Necesito el titulo" in out["final_response"]

    def test_requires_fecha_inicio(self):
        out = action_executor_node(
            _state("create_event", {"titulo": "E"}), None
        )
        assert "Necesito la fecha" in out["final_response"]

    def test_with_id_tarea(self, mongo_mock):
        tid = ObjectId()
        out = action_executor_node(
            _state("create_event", {
                "titulo": "E", "fecha_inicio": "2026-05-17T10:00",
                "id_tarea": str(tid),
            }),
            None,
        )
        assert "Evento creado" in out["final_response"]


class TestUpdateProject:
    def test_updates_with_allowed_fields(self, mongo_mock):
        pid = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({
            "_id": pid, "titulo": "P", "estado": "Activo", "usuario_id": USER_ID,
        })
        out = action_executor_node(
            _state("update_project", {"project_id": str(pid), "titulo": "Nuevo"}),
            None,
        )
        assert "actualizado" in out["final_response"]

    def test_no_fields_to_update(self, mongo_mock):
        pid = ObjectId()
        out = action_executor_node(
            _state("update_project", {"project_id": str(pid)}),
            None,
        )
        assert "No se indicaron campos" in out["final_response"]


class TestUpdateGoal:
    def test_updates_with_progress(self, mongo_mock):
        gid = ObjectId()
        mongo_mock.local_db["Goals"].insert_one({"_id": gid, "titulo": "G", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("update_goal", {"goal_id": str(gid), "progreso": "75"}),
            None,
        )
        assert "actualizado" in out["final_response"]

    def test_no_fields(self, mongo_mock):
        gid = ObjectId()
        out = action_executor_node(
            _state("update_goal", {"goal_id": str(gid)}), None
        )
        assert "No se indicaron campos" in out["final_response"]


class TestUpdateTask:
    def test_updates(self, mongo_mock):
        tid = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": tid, "contenido": "x", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("update_task", {"task_id": str(tid), "contenido": "y"}),
            None,
        )
        assert "actualizada" in out["final_response"]

    def test_no_fields(self, mongo_mock):
        tid = ObjectId()
        out = action_executor_node(
            _state("update_task", {"task_id": str(tid)}), None
        )
        assert "No se indicaron campos" in out["final_response"]


class TestMarkTaskComplete:
    def test_marks_completed(self, mongo_mock):
        tid = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": tid, "contenido": "x", "usuario_id": USER_ID, "estado": "pendiente"})
        out = action_executor_node(
            _state("mark_task_complete", {"task_id": str(tid)}), None
        )
        assert "completada" in out["final_response"]


class TestDeleteOperations:
    def test_delete_project_requires_confirmation(self, mongo_mock):
        pid = ObjectId()
        state = _state("delete_project", {"project_id": str(pid)})
        state["action_confirmed"] = False
        out = action_executor_node(state, None)
        assert "confirmacion" in out["final_response"]

    def test_delete_project_cascade(self, mongo_mock):
        pid = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({"_id": pid, "titulo": "P", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("delete_project", {"project_id": str(pid)}), None
        )
        assert "eliminado" in out["final_response"]
        assert mongo_mock.local_db["Projects"].count_documents({"_id": pid}) == 0

    def test_delete_goal_cascade(self, mongo_mock):
        gid = ObjectId()
        mongo_mock.local_db["Goals"].insert_one({"_id": gid, "titulo": "G", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("delete_goal", {"goal_id": str(gid)}), None
        )
        assert "eliminado" in out["final_response"]

    def test_delete_task(self, mongo_mock):
        tid = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": tid, "contenido": "x", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("delete_task", {"task_id": str(tid)}), None
        )
        assert "eliminada" in out["final_response"]

    def test_delete_event(self, mongo_mock):
        eid = ObjectId()
        mongo_mock.local_db["Events"].insert_one({"_id": eid, "titulo": "E", "usuario_id": USER_ID})
        out = action_executor_node(
            _state("delete_event", {"event_id": str(eid)}), None
        )
        assert "eliminado" in out["final_response"]


class TestEdgeCases:
    def test_no_action_name(self):
        state = {"user_id": USER_ID, "action_confirmed": True, "context_json": "{}"}
        out = action_executor_node(state, None)
        assert "No se detecto" in out["final_response"]

    def test_unknown_action(self):
        out = action_executor_node(
            _state("desconocida", {}), None,
        )
        assert "no soportada" in out["final_response"]

    def test_exception_in_model_caught(self, mongo_mock, monkeypatch):
        from model.project_model import ProjectModel

        def _boom(d):
            raise RuntimeError("db fail")

        monkeypatch.setattr(ProjectModel, "insert_project", staticmethod(_boom))
        out = action_executor_node(
            _state("create_project", {"titulo": "P"}), None,
        )
        assert "No pude ejecutar" in out["final_response"]


# ---------------------------------------------------------------------------
# Cascadas
# ---------------------------------------------------------------------------


class TestCascades:
    def test_delete_project_cascade_helper(self, mongo_mock):
        pid = ObjectId()
        gid = ObjectId()
        tid = ObjectId()
        did = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({"_id": pid, "titulo": "P", "usuario_id": USER_ID})
        mongo_mock.local_db["Goals"].insert_one({"_id": gid, "titulo": "G", "project_id": pid, "usuario_id": USER_ID})
        mongo_mock.local_db["Tasks"].insert_one({"_id": tid, "contenido": "T", "objetivo_id": gid, "usuario_id": USER_ID})
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": did, "project_id": pid, "original_name": "x", "usuario_id": USER_ID,
        })

        _delete_project_cascade(str(pid), USER_ID)

        assert mongo_mock.local_db["Projects"].count_documents({}) == 0
        assert mongo_mock.local_db["Goals"].count_documents({}) == 0
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 0
        assert mongo_mock.local_db["ProjectDocuments"].count_documents({}) == 0

    def test_delete_goal_cascade_only_removes_own_tasks(self, mongo_mock):
        g1 = ObjectId()
        g2 = ObjectId()
        mongo_mock.local_db["Goals"].insert_many([
            {"_id": g1, "titulo": "G1", "usuario_id": USER_ID},
            {"_id": g2, "titulo": "G2", "usuario_id": USER_ID},
        ])
        mongo_mock.local_db["Tasks"].insert_many([
            {"_id": ObjectId(), "contenido": "t1", "objetivo_id": g1, "usuario_id": USER_ID},
            {"_id": ObjectId(), "contenido": "t2", "objetivo_id": g2, "usuario_id": USER_ID},
        ])
        _delete_goal_cascade(str(g1), USER_ID)
        assert mongo_mock.local_db["Goals"].count_documents({"_id": g2}) == 1
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 1
