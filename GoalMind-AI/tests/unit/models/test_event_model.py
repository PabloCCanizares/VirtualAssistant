"""Bateria del modelo `eventModel` sobre `mongomock`."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.event_model import eventModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_event(mongo_mock, titulo="ev", **extra):
    e = {"_id": ObjectId(), "titulo": titulo, "usuario_id": USER_ID, **extra}
    mongo_mock.local_db["Events"].insert_one(e)
    return e


class TestQueries:
    def test_get_all_events(self, mongo_mock):
        _insert_event(mongo_mock, "a")
        _insert_event(mongo_mock, "b")
        assert len(eventModel.get_all_events()) == 2

    def test_get_events_by_task(self, mongo_mock):
        tid = ObjectId()
        _insert_event(mongo_mock, id_tarea=tid)
        _insert_event(mongo_mock, id_tarea=ObjectId())
        assert len(eventModel.get_events_by_task(tid)) == 1

    def test_get_events_by_task_supports_reference_schema(self, mongo_mock):
        tid = ObjectId()
        _insert_event(mongo_mock, referencia_id=tid, referencia_tipo="tarea")
        _insert_event(mongo_mock, referencia_id=ObjectId(), referencia_tipo="tarea")
        assert len(eventModel.get_events_by_task(tid)) == 1

    def test_get_events_by_task_invalid_id(self, mongo_mock):
        assert eventModel.get_events_by_task("bad") == []

    def test_get_events_by_goal(self, mongo_mock):
        gid = ObjectId()
        _insert_event(mongo_mock, id_objetivo=gid)
        assert len(eventModel.get_events_by_goal(gid)) == 1

    def test_get_events_by_goal_supports_reference_schema(self, mongo_mock):
        gid = ObjectId()
        _insert_event(mongo_mock, referencia_id=gid, referencia_tipo="objetivo")
        assert len(eventModel.get_events_by_goal(gid)) == 1

    def test_get_events_by_goal_invalid_id(self, mongo_mock):
        assert eventModel.get_events_by_goal("bad") == []

    def test_get_event_by_id(self, mongo_mock):
        e = _insert_event(mongo_mock)
        assert eventModel.get_event_by_id(e["_id"]) is not None

    def test_get_event_by_id_invalid_returns_none(self, mongo_mock):
        assert eventModel.get_event_by_id("bad-id") is None

    def test_get_events_by_user(self, mongo_mock):
        _insert_event(mongo_mock)
        assert len(eventModel.get_events_by_user(USER_ID)) == 1

    def test_get_events_by_type(self, mongo_mock):
        _insert_event(mongo_mock, tipo_evento="trabajo")
        _insert_event(mongo_mock, tipo_evento="personal")
        assert len(eventModel.get_events_by_type("trabajo")) == 1


class TestInsertUpdateDelete:
    def test_insert_event(self, mongo_mock):
        eid = eventModel.insert_event({"titulo": "x"})
        assert mongo_mock.local_db["Events"].find_one({"_id": eid})["titulo"] == "x"

    def test_insert_event_normalizes_legacy_task_reference(self, mongo_mock):
        tid = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({
            "_id": tid,
            "contenido": "T",
            "usuario_id": USER_ID,
            "event_ids": [],
        })
        eid = eventModel.insert_event({"titulo": "x", "id_tarea": str(tid)})
        event = mongo_mock.local_db["Events"].find_one({"_id": eid})
        assert "id_tarea" not in event
        assert event["referencia_tipo"] == "tarea"
        assert str(event["referencia_id"]) == str(tid)
        task = mongo_mock.local_db["Tasks"].find_one({"_id": tid})
        assert str(eid) in [str(item) for item in task["event_ids"]]

    def test_insert_event_preserves_usuario_id(self, mongo_mock):
        uid = "custom"
        eid = eventModel.insert_event({"titulo": "y", "usuario_id": uid})
        assert mongo_mock.local_db["Events"].find_one({"_id": eid})["usuario_id"] == uid

    def test_update_event(self, mongo_mock):
        e = _insert_event(mongo_mock, "viejo")
        eventModel.update_event(e["_id"], {"titulo": "nuevo"})
        assert mongo_mock.local_db["Events"].find_one({"_id": e["_id"]})["titulo"] == "nuevo"

    def test_delete_event(self, mongo_mock):
        e = _insert_event(mongo_mock)
        eventModel.delete_event(e["_id"])
        assert mongo_mock.local_db["Events"].find_one({"_id": e["_id"]}) is None

    def test_delete_events_by_ids(self, mongo_mock):
        e1 = _insert_event(mongo_mock)
        e2 = _insert_event(mongo_mock)
        deleted = eventModel.delete_events_by_ids([str(e1["_id"]), str(e2["_id"])])
        assert deleted == 2

    def test_delete_events_by_invalid_ids(self, mongo_mock):
        assert eventModel.delete_events_by_ids(["not-an-oid"]) == 0
