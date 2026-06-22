"""Bateria del modelo `CategoryModel` sobre `mongomock`."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.category_model import CategoryModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_category(mongo_mock, name="trabajo"):
    c = {"_id": ObjectId(), "name": name, "usuario_id": USER_ID}
    mongo_mock.local_db["Categories"].insert_one(c)
    return c


class TestInsertCategory:
    def test_inserts_new(self, mongo_mock):
        out = CategoryModel.insert_category("nueva")
        assert out is not None
        assert out["name"] == "nueva"

    def test_rejects_duplicate_case_insensitive(self, mongo_mock):
        CategoryModel.insert_category("Trabajo")
        # Misma cadena en otro case devuelve None
        assert CategoryModel.insert_category("TRABAJO") is None


class TestRead:
    def test_get_all_categories(self, mongo_mock):
        _insert_category(mongo_mock, "a")
        _insert_category(mongo_mock, "b")
        assert len(CategoryModel.get_all_categories()) == 2

    def test_get_category_by_id(self, mongo_mock):
        c = _insert_category(mongo_mock)
        assert CategoryModel.get_category_by_id(c["_id"]) is not None
        assert CategoryModel.get_category_by_id(str(c["_id"])) is not None

    def test_get_categories_by_ids(self, mongo_mock):
        c1 = _insert_category(mongo_mock, "a")
        c2 = _insert_category(mongo_mock, "b")
        out = CategoryModel.get_categories_by_ids([str(c1["_id"]), str(c2["_id"])])
        assert len(out) == 2

    def test_get_categories_by_ids_empty(self, mongo_mock):
        assert CategoryModel.get_categories_by_ids([]) == []

    def test_get_categories_by_ids_filters_invalid(self, mongo_mock):
        c = _insert_category(mongo_mock)
        out = CategoryModel.get_categories_by_ids(["bad", str(c["_id"])])
        assert len(out) == 1

    def test_get_categories_by_ids_all_invalid_returns_empty(self, mongo_mock):
        _insert_category(mongo_mock)
        assert CategoryModel.get_categories_by_ids(["bad"]) == []


class TestSearch:
    def test_search_by_name(self, mongo_mock):
        _insert_category(mongo_mock, "trabajo")
        _insert_category(mongo_mock, "personal")
        out = CategoryModel.search_by_name("trab")
        assert len(out) == 1

    def test_search_empty_returns_all(self, mongo_mock):
        _insert_category(mongo_mock, "a")
        _insert_category(mongo_mock, "b")
        assert len(CategoryModel.search_by_name("")) == 2


class TestUpdate:
    def test_update_changes_name(self, mongo_mock):
        c = _insert_category(mongo_mock)
        out = CategoryModel.update_category(c["_id"], "renombrada")
        assert out["name"] == "renombrada"

    def test_update_rejects_duplicate_name(self, mongo_mock):
        _insert_category(mongo_mock, "a")
        c2 = _insert_category(mongo_mock, "b")
        assert CategoryModel.update_category(c2["_id"], "a") is None


class TestDelete:
    def test_delete_returns_true(self, mongo_mock):
        c = _insert_category(mongo_mock)
        assert CategoryModel.delete_category(c["_id"]) is True

    def test_delete_invalid_id_returns_false(self, mongo_mock):
        assert CategoryModel.delete_category("not-an-oid") is False


class TestExistsAndUsage:
    def test_exists_by_name(self, mongo_mock):
        _insert_category(mongo_mock, "Trabajo")
        assert CategoryModel.exists_by_name("TRABAJO") is True
        assert CategoryModel.exists_by_name("otra") is False

    def test_get_category_usage_counts(self, mongo_mock):
        cat_id = ObjectId()
        _insert_category(mongo_mock, "x")  # not connected
        # 2 goals, 1 task, 3 projects con la categoria
        for _ in range(2):
            mongo_mock.local_db["Goals"].insert_one({"_id": ObjectId(), "categorias": [cat_id], "usuario_id": USER_ID})
        mongo_mock.local_db["Tasks"].insert_one({"_id": ObjectId(), "categorias": [cat_id], "usuario_id": USER_ID})
        for _ in range(3):
            mongo_mock.local_db["Projects"].insert_one({"_id": ObjectId(), "categorias": [cat_id], "usuario_id": USER_ID})
        usage = CategoryModel.get_category_usage(cat_id)
        assert usage == {"goals": 2, "tasks": 1, "projects": 3, "total": 6}

    def test_get_category_usage_invalid_id(self, mongo_mock):
        assert CategoryModel.get_category_usage("bad") == {"goals": 0, "tasks": 0, "projects": 0, "total": 0}
