"""Tests adicionales del `eventModel`: cobertura de ramas con remoto activo."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.event_model import eventModel

pytestmark = pytest.mark.usefixtures("mongo_mock")


class TestRemoteSyncBranches:
    def test_insert_with_remote_sync(self, mongo_mock):
        eid = eventModel.insert_event({"titulo": "x", "usuario_id": "66ffbbbbbbbbbbbbbbbb0100"})
        # El remoto recibe una copia
        assert mongo_mock.remote_db["Events"].find_one({"_id": eid}) is not None

    def test_update_with_remote_sync(self, mongo_mock):
        e = {"_id": ObjectId(), "titulo": "viejo", "usuario_id": "66ffbbbbbbbbbbbbbbbb0100"}
        mongo_mock.local_db["Events"].insert_one(e)
        mongo_mock.remote_db["Events"].insert_one(dict(e))
        eventModel.update_event(e["_id"], {"titulo": "nuevo"})
        assert mongo_mock.remote_db["Events"].find_one({"_id": e["_id"]})["titulo"] == "nuevo"

    def test_delete_with_remote_sync(self, mongo_mock):
        e = {"_id": ObjectId(), "titulo": "x", "usuario_id": "66ffbbbbbbbbbbbbbbbb0100"}
        mongo_mock.local_db["Events"].insert_one(e)
        mongo_mock.remote_db["Events"].insert_one(dict(e))
        eventModel.delete_event(e["_id"])
        assert mongo_mock.remote_db["Events"].find_one({"_id": e["_id"]}) is None
