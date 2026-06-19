"""Tests para context_repository._serialize_value: conversion segura a JSON."""

from __future__ import annotations

import json
from datetime import datetime

from bson import ObjectId

from ai.repositories import context_repository as cr


class TestSerializeValue:
    def test_object_id_to_str(self):
        oid = ObjectId()
        assert cr._serialize_value(oid) == str(oid)

    def test_datetime_to_iso(self):
        dt = datetime(2024, 1, 2, 3, 4, 5)
        assert cr._serialize_value(dt) == dt.isoformat()

    def test_primitive_passthrough(self):
        assert cr._serialize_value(1) == 1
        assert cr._serialize_value("x") == "x"
        assert cr._serialize_value(None) is None
        assert cr._serialize_value(3.14) == 3.14

    def test_dict_recursive(self):
        oid = ObjectId()
        out = cr._serialize_value({"id": oid, "n": 1})
        assert out == {"id": str(oid), "n": 1}

    def test_list_recursive(self):
        oid = ObjectId()
        out = cr._serialize_value([oid, "x", 3])
        assert out == [str(oid), "x", 3]

    def test_nested_structure(self):
        oid = ObjectId()
        dt = datetime(2024, 1, 1)
        nested = {"items": [{"id": oid, "ts": dt}]}
        out = cr._serialize_value(nested)
        # debe ser totalmente serializable a JSON
        json.dumps(out)
        assert out == {"items": [{"id": str(oid), "ts": dt.isoformat()}]}


class TestLoadUserCollections:
    def test_unknown_collection_skipped(self, monkeypatch):
        # No mockeamos los modelos: con colecciones desconocidas, ningun loader corre.
        out_json = cr.load_user_collections("uid", ["does_not_exist"])
        out = json.loads(out_json)
        assert out == {"user_id": "uid"}

    def test_known_collection_invokes_loader(self, monkeypatch):
        called = []
        oid = ObjectId()

        def fake_projects(uid):
            called.append(uid)
            return [cr._serialize_value({"_id": oid, "titulo": "p1"})]

        monkeypatch.setitem(cr._COLLECTION_LOADERS, "projects", fake_projects)

        out_json = cr.load_user_collections("uid", ["projects"])
        out = json.loads(out_json)

        assert called == ["uid"]
        assert "projects" in out
        assert out["projects"][0]["titulo"] == "p1"
        assert out["projects"][0]["_id"] == str(oid)
