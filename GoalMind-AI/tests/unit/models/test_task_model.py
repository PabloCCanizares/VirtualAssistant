"""Bateria del modelo `TaskModel` sobre `mongomock`."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.task_model import TaskModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_task(mongo_mock, contenido="t", **extra):
    task = {"_id": ObjectId(), "contenido": contenido, "usuario_id": USER_ID, **extra}
    mongo_mock.local_db["Tasks"].insert_one(task)
    return task


class TestInsertTask:
    def test_inserts_and_sets_defaults(self, mongo_mock):
        out = TaskModel.insert_task({"contenido": "redactar"})
        assert "_id" in out
        assert "fecha_creacion" in out
        assert out["event_ids"] == []
        assert out["usuario_id"]
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 1

    def test_preserves_existing_fields(self, mongo_mock):
        existing_uid = ObjectId()
        data = {"contenido": "x", "usuario_id": existing_uid, "event_ids": [ObjectId()]}
        out = TaskModel.insert_task(data)
        assert out["usuario_id"] == existing_uid
        assert len(out["event_ids"]) == 1


class TestGetTaskById:
    def test_returns_existing(self, mongo_mock):
        t = _insert_task(mongo_mock, "hola")
        found = TaskModel.get_task_by_id(t["_id"])
        assert found is not None
        assert found["contenido"] == "hola"

    def test_returns_none_when_missing(self, mongo_mock):
        assert TaskModel.get_task_by_id(ObjectId()) is None

    def test_accepts_string_id(self, mongo_mock):
        t = _insert_task(mongo_mock, "x")
        found = TaskModel.get_task_by_id(str(t["_id"]))
        assert found["contenido"] == "x"


class TestGetTasksByCategory:
    def test_returns_only_matching_category(self, mongo_mock):
        cat = ObjectId()
        _insert_task(mongo_mock, "match", categorias=[cat])
        _insert_task(mongo_mock, "other", categorias=[ObjectId()])
        out = TaskModel.get_tasks_by_category(cat)
        assert len(out) == 1
        assert out[0]["contenido"] == "match"


class TestSearchTasks:
    def test_regex_partial_match(self, mongo_mock):
        _insert_task(mongo_mock, "redactar memoria")
        _insert_task(mongo_mock, "preparar slides")
        out = TaskModel.search_tasks(nombre="REDACT")
        assert len(out) == 1
        assert out[0]["contenido"] == "redactar memoria"

    def test_filter_by_category_ids(self, mongo_mock):
        cat = ObjectId()
        _insert_task(mongo_mock, "t1", categorias=[cat])
        _insert_task(mongo_mock, "t2", categorias=[ObjectId()])
        out = TaskModel.search_tasks(category_ids=[cat])
        assert len(out) == 1
        assert out[0]["contenido"] == "t1"

    def test_invalid_category_ids_filtered(self, mongo_mock):
        cat = ObjectId()
        _insert_task(mongo_mock, "t1", categorias=[cat])
        out = TaskModel.search_tasks(category_ids=["invalido", str(cat)])
        assert len(out) == 1

    def test_no_filters_returns_all(self, mongo_mock):
        _insert_task(mongo_mock, "t1")
        _insert_task(mongo_mock, "t2")
        assert len(TaskModel.search_tasks()) == 2


class TestGetTasksByGoal:
    def test_objectid_goal(self, mongo_mock):
        gid = ObjectId()
        _insert_task(mongo_mock, "t", objetivo_id=gid)
        out = TaskModel.get_tasks_by_goal(gid)
        assert len(out) == 1

    def test_string_goal(self, mongo_mock):
        gid = ObjectId()
        _insert_task(mongo_mock, "t", objetivo_id=gid)
        out = TaskModel.get_tasks_by_goal(str(gid))
        assert len(out) == 1

    def test_none_goal_returns_empty(self, mongo_mock):
        assert TaskModel.get_tasks_by_goal(None) == []


class TestDeleteTask:
    def test_deletes_local(self, mongo_mock):
        t = _insert_task(mongo_mock)
        TaskModel.delete_task(t["_id"])
        assert mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]}) is None

    def test_delete_handles_remote_exception(self, mongo_mock, monkeypatch):
        t = _insert_task(mongo_mock)

        def _boom(*a, **k):
            raise RuntimeError("net")

        # Sustituye delete_one en remoto por uno que falla.
        original = mongo_mock.remote_db["Tasks"].delete_one
        monkeypatch.setattr(
            mongo_mock.remote_db["Tasks"], "delete_one", _boom, raising=False
        )
        TaskModel.delete_task(t["_id"])
        assert mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]}) is None
        monkeypatch.setattr(
            mongo_mock.remote_db["Tasks"], "delete_one", original, raising=False
        )


class TestDeleteTasksByIds:
    def test_deletes_multiple(self, mongo_mock):
        ts = [_insert_task(mongo_mock, f"t{i}") for i in range(3)]
        deleted = TaskModel.delete_tasks_by_ids([t["_id"] for t in ts])
        assert deleted == 3
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 0

    def test_empty_list_returns_zero(self, mongo_mock):
        assert TaskModel.delete_tasks_by_ids([]) == 0


class TestUpdateTask:
    def test_updates_fields(self, mongo_mock):
        t = _insert_task(mongo_mock, "viejo")
        TaskModel.update_task(t["_id"], {"contenido": "nuevo"})
        found = mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]})
        assert found["contenido"] == "nuevo"

    def test_update_estado_recalculates_goal_progress(self, mongo_mock):
        # Seed: un goal y dos tasks
        goal_id = ObjectId()
        mongo_mock.local_db["Goals"].insert_one({"_id": goal_id, "titulo": "G", "usuario_id": USER_ID})
        _insert_task(mongo_mock, "t1", objetivo_id=goal_id, estado="completada")
        t2 = _insert_task(mongo_mock, "t2", objetivo_id=goal_id, estado="pendiente")

        TaskModel.update_task(t2["_id"], {"estado": "completada"})

        goal = mongo_mock.local_db["Goals"].find_one({"_id": goal_id})
        assert goal["progreso"] == 100.0


class TestRecalculateGoalProgress:
    def test_no_tasks_yields_zero(self, mongo_mock):
        goal_id = ObjectId()
        mongo_mock.local_db["Goals"].insert_one({"_id": goal_id, "titulo": "G", "usuario_id": USER_ID})
        out = TaskModel.recalculate_goal_progress(goal_id)
        assert out == 0.0

    def test_mixed_states(self, mongo_mock):
        goal_id = ObjectId()
        mongo_mock.local_db["Goals"].insert_one({"_id": goal_id, "titulo": "G", "usuario_id": USER_ID})
        _insert_task(mongo_mock, objetivo_id=goal_id, estado="completada")
        _insert_task(mongo_mock, objetivo_id=goal_id, estado="pendiente")
        out = TaskModel.recalculate_goal_progress(goal_id)
        assert out == 50.0


class TestEventAssociations:
    def test_add_event_to_task_addtoset(self, mongo_mock):
        t = _insert_task(mongo_mock)
        eid = ObjectId()
        TaskModel.add_event_to_task(t["_id"], eid)
        TaskModel.add_event_to_task(t["_id"], eid)  # duplicado
        found = mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]})
        assert found["event_ids"] == [eid]

    def test_remove_event_from_task(self, mongo_mock):
        eid = ObjectId()
        t = _insert_task(mongo_mock, event_ids=[eid, ObjectId()])
        TaskModel.remove_event_from_task(t["_id"], eid)
        found = mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]})
        assert eid not in found["event_ids"]


class TestAssignGoalToTasks:
    def test_assigns_goal_to_multiple_tasks(self, mongo_mock):
        ts = [_insert_task(mongo_mock, f"t{i}") for i in range(3)]
        goal_id = ObjectId()
        updated = TaskModel.assign_goal_to_tasks([t["_id"] for t in ts], goal_id)
        assert updated == 3
        for t in ts:
            found = mongo_mock.local_db["Tasks"].find_one({"_id": t["_id"]})
            assert found["objetivo_id"] == goal_id

    def test_empty_task_ids_does_nothing(self, mongo_mock):
        goal_id = ObjectId()
        assert TaskModel.assign_goal_to_tasks([], goal_id) == 0


class TestGetAllAndGetByUser:
    def test_get_all_tasks(self, mongo_mock):
        _insert_task(mongo_mock, "a")
        _insert_task(mongo_mock, "b")
        assert len(TaskModel.get_all_tasks()) == 2

    def test_get_task_by_user(self, mongo_mock):
        _insert_task(mongo_mock, "a")
        out = TaskModel.get_task_by_user(USER_ID)
        assert len(out) == 1
