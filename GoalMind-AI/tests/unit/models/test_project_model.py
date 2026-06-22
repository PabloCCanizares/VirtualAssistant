"""Bateria del modelo `ProjectModel` sobre `mongomock`."""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

from model.project_model import ProjectModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_project(mongo_mock, titulo="P", **extra):
    p = {"_id": ObjectId(), "titulo": titulo, "usuario_id": USER_ID, **extra}
    mongo_mock.local_db["Projects"].insert_one(p)
    return p


class TestQueries:
    def test_get_all_projects(self, mongo_mock):
        _insert_project(mongo_mock, "a")
        _insert_project(mongo_mock, "b")
        assert len(ProjectModel.get_all_projects()) == 2

    def test_get_by_user_id(self, mongo_mock):
        _insert_project(mongo_mock)
        assert len(ProjectModel.get_by_user_id(USER_ID)) == 1

    def test_get_project_by_id(self, mongo_mock):
        p = _insert_project(mongo_mock)
        assert ProjectModel.get_project_by_id(p["_id"]) is not None
        assert ProjectModel.get_project_by_id(str(p["_id"])) is not None

    def test_find_by_category(self, mongo_mock):
        cat = ObjectId()
        _insert_project(mongo_mock, categorias=[cat])
        _insert_project(mongo_mock, categorias=[ObjectId()])
        assert len(ProjectModel.find_by_category(cat)) == 1

    def test_search_by_categories_with_matches(self, mongo_mock):
        cat = ObjectId()
        _insert_project(mongo_mock, categorias=[cat])
        assert len(ProjectModel.search_by_categories([str(cat)])) == 1

    def test_search_by_categories_empty(self, mongo_mock):
        _insert_project(mongo_mock)
        _insert_project(mongo_mock)
        assert len(ProjectModel.search_by_categories([])) == 2

    def test_search_by_categories_all_invalid_returns_all(self, mongo_mock):
        _insert_project(mongo_mock)
        assert len(ProjectModel.search_by_categories(["bad-id"])) == 1


class TestInsertProject:
    def test_inserts_with_defaults(self, mongo_mock):
        out = ProjectModel.insert_project({"titulo": "p1"})
        assert "_id" in out
        assert "created_at" in out
        assert out["usuario_id"]

    def test_preserves_existing_created_at(self, mongo_mock):
        ts = datetime(2026, 1, 1)
        out = ProjectModel.insert_project({"titulo": "p", "created_at": ts})
        assert out["created_at"] == ts


class TestUpdateProject:
    def test_updates_fields_with_date_parsing(self, mongo_mock):
        p = _insert_project(mongo_mock)
        ProjectModel.update_project(p["_id"], {"titulo": "nuevo", "fecha_inicio": "2026-05-01"})
        found = mongo_mock.local_db["Projects"].find_one({"_id": p["_id"]})
        assert found["titulo"] == "nuevo"
        assert isinstance(found["fecha_inicio"], datetime)

    def test_update_invalid_date_yields_none(self, mongo_mock):
        p = _insert_project(mongo_mock)
        ProjectModel.update_project(p["_id"], {"fecha_inicio": "bad-date"})
        found = mongo_mock.local_db["Projects"].find_one({"_id": p["_id"]})
        assert found["fecha_inicio"] is None

    def test_update_invalid_usuario_id_keeps_string(self, mongo_mock):
        p = _insert_project(mongo_mock)
        ProjectModel.update_project(p["_id"], {"usuario_id": "bad-id"})
        found = mongo_mock.local_db["Projects"].find_one({"_id": p["_id"]})
        # se conserva la cadena (la conversion fallo silenciosamente)
        assert found["usuario_id"] == "bad-id"


class TestDeleteProject:
    def test_delete_returns_true(self, mongo_mock):
        p = _insert_project(mongo_mock)
        assert ProjectModel.delete_project(p["_id"]) is True

    def test_delete_string_id(self, mongo_mock):
        p = _insert_project(mongo_mock)
        assert ProjectModel.delete_project(str(p["_id"])) is True

    def test_delete_missing_returns_false(self, mongo_mock):
        assert ProjectModel.delete_project(ObjectId()) is False

    def test_delete_none_returns_false(self, mongo_mock):
        assert ProjectModel.delete_project(None) is False


class TestCalculateProgress:
    def test_progress_from_goals_empty(self):
        assert ProjectModel.calculate_progress_from_goals([]) == 0.0

    def test_progress_from_goals_average(self):
        goals = [{"progreso": 80}, {"progreso": 40}]
        assert ProjectModel.calculate_progress_from_goals(goals) == 60.0

    def test_progress_from_goals_handles_invalid_values(self):
        goals = [{"progreso": "no-numero"}, {"progreso": 100}]
        assert ProjectModel.calculate_progress_from_goals(goals) == 50.0

    def test_calculate_progress_full_path(self, mongo_mock):
        p = _insert_project(mongo_mock)
        # 2 goals con progreso
        mongo_mock.local_db["Goals"].insert_many([
            {"_id": ObjectId(), "titulo": "g1", "project_id": p["_id"], "progreso": 100, "usuario_id": USER_ID},
            {"_id": ObjectId(), "titulo": "g2", "project_id": p["_id"], "progreso": 50, "usuario_id": USER_ID},
        ])
        progress = ProjectModel.calculate_progress(p["_id"])
        assert progress == 75.0
