"""Bateria del modelo `GoalModel` sobre `mongomock`."""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

from model.goal_model import GoalModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_goal(mongo_mock, titulo="g", **extra):
    g = {"_id": ObjectId(), "titulo": titulo, "usuario_id": USER_ID, **extra}
    mongo_mock.local_db["Goals"].insert_one(g)
    return g


class TestInsertGoal:
    def test_inserts_with_defaults(self, mongo_mock):
        out = GoalModel.insert_goal({"titulo": "g1", "project_id": ObjectId()})
        assert "_id" in out
        assert "created_at" in out
        assert out["event_ids"] == []

    def test_inserts_with_string_project_id(self, mongo_mock):
        pid = str(ObjectId())
        out = GoalModel.insert_goal({"titulo": "g", "project_id": pid})
        assert isinstance(out["project_id"], ObjectId)

    def test_inserts_with_dollar_ref_alias_strips_prefix(self, mongo_mock):
        pid = ObjectId()
        out = GoalModel.insert_goal({"titulo": "g", "project_id": f"$ref:{pid}"})
        assert out["project_id"] == pid


class TestQueries:
    def test_get_all_goals(self, mongo_mock):
        _insert_goal(mongo_mock, "a")
        _insert_goal(mongo_mock, "b")
        assert len(GoalModel.get_all_goals()) == 2

    def test_get_by_user_id(self, mongo_mock):
        _insert_goal(mongo_mock)
        assert len(GoalModel.get_by_user_id(USER_ID)) == 1

    def test_get_goal_by_id(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        assert GoalModel.get_goal_by_id(g["_id"]) is not None
        assert GoalModel.get_goal_by_id(str(g["_id"])) is not None

    def test_get_by_project_with_objectid(self, mongo_mock):
        pid = ObjectId()
        _insert_goal(mongo_mock, project_id=pid)
        _insert_goal(mongo_mock, project_id=ObjectId())
        assert len(GoalModel.get_by_project(pid)) == 1

    def test_get_by_project_with_string(self, mongo_mock):
        pid = ObjectId()
        _insert_goal(mongo_mock, project_id=pid)
        assert len(GoalModel.get_by_project(str(pid))) == 1

    def test_get_by_project_none_returns_empty(self, mongo_mock):
        assert GoalModel.get_by_project(None) == []

    def test_find_by_category(self, mongo_mock):
        cat = ObjectId()
        _insert_goal(mongo_mock, categorias=[cat])
        _insert_goal(mongo_mock, categorias=[ObjectId()])
        assert len(GoalModel.find_by_category(cat)) == 1

    def test_search_by_categories_with_invalid_filtered(self, mongo_mock):
        cat = ObjectId()
        _insert_goal(mongo_mock, categorias=[cat])
        # invalido se filtra; sigue encontrando el valido
        assert len(GoalModel.search_by_categories(["invalido", str(cat)])) == 1

    def test_search_by_categories_empty_returns_all(self, mongo_mock):
        _insert_goal(mongo_mock)
        _insert_goal(mongo_mock)
        assert len(GoalModel.search_by_categories([])) == 2

    def test_search_by_categories_only_invalid_returns_all(self, mongo_mock):
        _insert_goal(mongo_mock)
        assert len(GoalModel.search_by_categories(["bad-id"])) == 1

    def test_search_by_name(self, mongo_mock):
        _insert_goal(mongo_mock, titulo="redactar memoria")
        _insert_goal(mongo_mock, titulo="otro")
        out = GoalModel.search_by_name("REDACT")
        assert len(out) == 1

    def test_search_by_name_empty_returns_empty(self, mongo_mock):
        _insert_goal(mongo_mock)
        assert GoalModel.search_by_name("") == []


class TestUpdateGoal:
    def test_updates_fields_and_dates(self, mongo_mock):
        g = _insert_goal(mongo_mock, titulo="viejo")
        GoalModel.update_goal(g["_id"], {"titulo": "nuevo", "fecha_inicio": "2026-01-01"})
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert found["titulo"] == "nuevo"
        assert isinstance(found["fecha_inicio"], datetime)

    def test_update_invalid_date_yields_none(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        GoalModel.update_goal(g["_id"], {"fecha_inicio": "not-a-date"})
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert found["fecha_inicio"] is None

    def test_update_progreso_string(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        GoalModel.update_goal(g["_id"], {"progreso": "85"})
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert found["progreso"] == 85.0

    def test_update_invalid_project_id_yields_none(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        GoalModel.update_goal(g["_id"], {"project_id": "bad-id"})
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert found["project_id"] is None


class TestEventAssociations:
    def test_add_event_to_goal_dedupes(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        eid = ObjectId()
        GoalModel.add_event_to_goal(g["_id"], eid)
        GoalModel.add_event_to_goal(g["_id"], eid)
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert found["event_ids"] == [eid]

    def test_remove_event_from_goal(self, mongo_mock):
        eid = ObjectId()
        g = _insert_goal(mongo_mock, event_ids=[eid])
        GoalModel.remove_event_from_goal(g["_id"], eid)
        found = mongo_mock.local_db["Goals"].find_one({"_id": g["_id"]})
        assert eid not in (found.get("event_ids") or [])


class TestDeleteGoal:
    def test_delete_returns_true(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        assert GoalModel.delete_goal(g["_id"]) is True
        assert mongo_mock.local_db["Goals"].count_documents({}) == 0

    def test_delete_accepts_string(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        assert GoalModel.delete_goal(str(g["_id"])) is True

    def test_delete_returns_false_when_missing(self, mongo_mock):
        assert GoalModel.delete_goal(ObjectId()) is False

    def test_delete_none_returns_false(self, mongo_mock):
        assert GoalModel.delete_goal(None) is False


class TestDeleteGoalsByIds:
    def test_deletes_multiple(self, mongo_mock):
        ids = [_insert_goal(mongo_mock)["_id"] for _ in range(3)]
        assert GoalModel.delete_goals_by_ids(ids) == 3

    def test_handles_mixed_string_and_oid(self, mongo_mock):
        g = _insert_goal(mongo_mock)
        # Pass string id
        assert GoalModel.delete_goals_by_ids([str(g["_id"])]) == 1

    def test_skip_empty_inputs(self, mongo_mock):
        assert GoalModel.delete_goals_by_ids([None, "", 0]) == 0
