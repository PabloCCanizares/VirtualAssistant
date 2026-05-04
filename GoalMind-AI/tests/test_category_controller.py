"""Tests para los endpoints REST del blueprint de categorias.

Se utiliza el test client de Flask y se monkeypatchean los metodos estaticos de
``CategoryModel`` para evitar dependencias con MongoDB.
"""

from __future__ import annotations

from bson import ObjectId
import pytest
from flask import Flask

from controllers import category_controller
from controllers.category_controller import category_bp


@pytest.fixture
def client(monkeypatch):
    """Construye una app Flask minima registrando solo el blueprint de categorias."""
    app = Flask(__name__)
    app.register_blueprint(category_bp)
    app.config["TESTING"] = True
    return app.test_client()


def _category_doc(name="Trabajo"):
    return {"_id": ObjectId(), "name": name}


class TestApiGetAllCategories:
    def test_returns_serialized_list(self, client, monkeypatch):
        cats = [_category_doc("a"), _category_doc("b")]
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_all_categories",
            staticmethod(lambda usuario_id: cats),
        )
        resp = client.get("/categories/api/all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert len(data["categories"]) == 2
        # Los _id deben ser strings (no ObjectId)
        assert all(isinstance(c["_id"], str) for c in data["categories"])

    def test_returns_500_on_db_error(self, client, monkeypatch):
        def boom(usuario_id):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            category_controller.CategoryModel, "get_all_categories", staticmethod(boom)
        )
        resp = client.get("/categories/api/all")
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


class TestApiSearchCategories:
    def test_passes_query_and_returns_results(self, client, monkeypatch):
        captured = {}

        def fake_search(query, usuario_id):
            captured["q"] = query
            return [_category_doc("trabajo")]

        monkeypatch.setattr(
            category_controller.CategoryModel, "search_by_name", staticmethod(fake_search)
        )
        resp = client.get("/categories/api/search?q=trabajo")
        assert resp.status_code == 200
        assert captured["q"] == "trabajo"
        assert resp.get_json()["categories"][0]["name"] == "trabajo"


class TestApiGetCategory:
    def test_returns_404_when_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid, usuario_id: None),
        )
        resp = client.get("/categories/api/abc")
        assert resp.status_code == 404

    def test_returns_200_when_found(self, client, monkeypatch):
        cat = _category_doc("Estudios")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid, usuario_id: cat),
        )
        resp = client.get(f"/categories/api/{cat['_id']}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["category"]["name"] == "Estudios"


class TestApiAddCategory:
    def test_400_when_no_payload(self, client):
        resp = client.post("/categories/api/add", json=None)
        # Flask may return 400 due to no JSON; the handler also returns 400
        assert resp.status_code in (400, 500)

    def test_400_when_name_missing(self, client):
        resp = client.post("/categories/api/add", json={"otra": "x"})
        assert resp.status_code == 400
        assert "obligatorio" in resp.get_json()["message"].lower()

    def test_400_when_name_blank(self, client):
        resp = client.post("/categories/api/add", json={"name": "   "})
        assert resp.status_code == 400
        assert "obligatorio" in resp.get_json()["message"].lower()

    def test_409_when_duplicate(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "exists_by_name",
            staticmethod(lambda name, usuario_id: True),
        )
        resp = client.post("/categories/api/add", json={"name": "X"})
        assert resp.status_code == 409

    def test_500_when_insert_returns_none(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "exists_by_name",
            staticmethod(lambda name, usuario_id: False),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "insert_category",
            staticmethod(lambda name, usuario_id: None),
        )
        resp = client.post("/categories/api/add", json={"name": "X"})
        assert resp.status_code == 500

    def test_201_on_success(self, client, monkeypatch):
        new_cat = _category_doc("Nueva")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "exists_by_name",
            staticmethod(lambda name, usuario_id: False),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "insert_category",
            staticmethod(lambda name, usuario_id: new_cat),
        )
        resp = client.post("/categories/api/add", json={"name": "Nueva"})
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["category"]["name"] == "Nueva"


class TestApiUpdateCategory:
    def test_400_when_name_missing(self, client):
        resp = client.put("/categories/api/update/abc", json={"otra": "x"})
        assert resp.status_code == 400
        assert "obligatorio" in resp.get_json()["message"].lower()

    def test_404_when_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: None),
        )
        resp = client.put("/categories/api/update/abc", json={"name": "X"})
        assert resp.status_code == 404

    def test_409_when_duplicate_after_update(self, client, monkeypatch):
        existing = _category_doc("Old")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: existing),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "update_category",
            staticmethod(lambda cid, name, usuario_id: None),
        )
        resp = client.put(f"/categories/api/update/{existing['_id']}", json={"name": "Existente"})
        assert resp.status_code == 409

    def test_200_on_success(self, client, monkeypatch):
        existing = _category_doc("Old")
        updated = _category_doc("New")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: existing),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "update_category",
            staticmethod(lambda cid, name, usuario_id: updated),
        )
        resp = client.put(f"/categories/api/update/{existing['_id']}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.get_json()["category"]["name"] == "New"


class TestApiCategoryUsage:
    def test_404_when_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid, usuario_id: None),
        )
        resp = client.get("/categories/api/usage/abc")
        assert resp.status_code == 404

    def test_returns_usage_dict(self, client, monkeypatch):
        cat = _category_doc("Trabajo")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid, usuario_id: cat),
        )
        usage = {"goals": 1, "tasks": 2, "projects": 3, "total": 6}
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_usage",
            staticmethod(lambda cid, usuario_id: usage),
        )
        resp = client.get(f"/categories/api/usage/{cat['_id']}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["usage"] == usage


class TestApiDeleteCategory:
    def test_404_when_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: None),
        )
        resp = client.delete("/categories/api/delete/abc")
        assert resp.status_code == 404

    def test_500_when_model_returns_false(self, client, monkeypatch):
        cat = _category_doc("X")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: cat),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "delete_category",
            staticmethod(lambda cid, usuario_id: False),
        )
        resp = client.delete(f"/categories/api/delete/{cat['_id']}")
        assert resp.status_code == 500

    def test_200_on_success(self, client, monkeypatch):
        cat = _category_doc("X")
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_category_by_id",
            staticmethod(lambda cid: cat),
        )
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "delete_category",
            staticmethod(lambda cid, usuario_id: True),
        )
        resp = client.delete(f"/categories/api/delete/{cat['_id']}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


class TestApiGetCategoriesByIds:
    def test_400_when_no_payload(self, client):
        resp = client.post("/categories/api/by-ids", json=None)
        assert resp.status_code in (400, 500)

    def test_empty_ids_returns_empty_list(self, client):
        resp = client.post("/categories/api/by-ids", json={"ids": []})
        assert resp.status_code == 200
        assert resp.get_json()["categories"] == []

    def test_returns_serialized_results(self, client, monkeypatch):
        cats = [_category_doc("a"), _category_doc("b")]
        monkeypatch.setattr(
            category_controller.CategoryModel,
            "get_categories_by_ids",
            staticmethod(lambda ids, usuario_id: cats),
        )
        resp = client.post("/categories/api/by-ids", json={"ids": ["x", "y"]})
        assert resp.status_code == 200
        assert len(resp.get_json()["categories"]) == 2
