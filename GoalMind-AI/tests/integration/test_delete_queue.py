"""Tests de integracion sobre la cola de borrados (`DeleteQueue`).

Escenario clave: el usuario borra mientras esta sin conexion al remoto.
Cuando recupera la conexion, los borrados deben propagarse al remoto y
el documento NO debe "resucitar" al volver a hacer pull.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

pytestmark = pytest.mark.integration

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"


class TestQueueDeletion:
    """`queue_deletion` registra en `DeleteQueue` y borra local inmediatamente."""

    def test_records_target_and_collection(self, mongo_mock):
        from database.mongo_conn import queue_deletion

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "a borrar"})

        assert queue_deletion("Tasks", _id) is True

        queue_doc = mongo_mock.local_db["DeleteQueue"].find_one({"collection": "Tasks"})
        assert queue_doc is not None
        assert queue_doc["target_id"] == str(_id)
        assert isinstance(queue_doc["deleted_at"], datetime)

    def test_also_removes_local_document(self, mongo_mock):
        from database.mongo_conn import queue_deletion

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "bye"})
        queue_deletion("Tasks", _id)
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id}) is None

    def test_idempotent_on_setOnInsert(self, mongo_mock):
        from database.mongo_conn import queue_deletion

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "x"})
        queue_deletion("Tasks", _id)
        queue_deletion("Tasks", _id)  # segunda llamada
        # Solo debe haber un registro en DeleteQueue
        assert mongo_mock.local_db["DeleteQueue"].count_documents({"collection": "Tasks"}) == 1


class TestFlushQueue:
    """`flush_deletion_queue` propaga al remoto y limpia los completados."""

    def test_propagates_deletion_to_remote_then_clears(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "borrame", "usuario_id": USER_ID_STR})
        mongo_mock.remote_db["Tasks"].insert_one({"_id": _id, "contenido": "borrame", "usuario_id": USER_ID_STR})

        mongo_conn.queue_deletion("Tasks", _id)
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id}) is not None  # aun no propagado

        removed = mongo_conn.flush_deletion_queue()
        assert removed == 1
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id}) is None
        # Y el registro de la cola desaparece
        assert mongo_mock.local_db["DeleteQueue"].count_documents({}) == 0

    def test_already_absent_remote_document_clears_queue(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)
        target_id = ObjectId()
        mongo_mock.local_db["DeleteQueue"].insert_one({
            "_id": f"Tasks:{target_id}",
            "collection": "Tasks",
            "target_id": str(target_id),
            "deleted_at": datetime.utcnow(),
        })

        assert mongo_conn.flush_deletion_queue() == 1
        assert mongo_mock.local_db["DeleteQueue"].count_documents({}) == 0

    def test_propagation_does_work_when_remote_id_is_string(self, mongo_mock, monkeypatch):
        """Variante reproducible: si el documento remoto tiene `_id` como string
        (no ObjectId), el dedup no causa problema y la propagacion si funciona.
        Esto demuestra que el bug es especifico a la combinacion string/ObjectId.
        """
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id_str = "task-string-id"
        mongo_mock.local_db["Tasks"].insert_one(
            {"_id": _id_str, "contenido": "borrame", "usuario_id": USER_ID_STR}
        )
        mongo_mock.remote_db["Tasks"].insert_one(
            {"_id": _id_str, "contenido": "borrame", "usuario_id": USER_ID_STR}
        )

        mongo_conn.queue_deletion("Tasks", _id_str)
        removed = mongo_conn.flush_deletion_queue()
        assert removed == 1
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id_str}) is None
        assert mongo_mock.local_db["DeleteQueue"].count_documents({}) == 0

    def test_flush_without_remote_keeps_queue(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        # Forzamos a que no haya conexion remota
        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: False)

        _id = ObjectId()
        mongo_mock.local_db["DeleteQueue"].insert_one({
            "_id": f"Tasks:{_id}",
            "collection": "Tasks",
            "target_id": str(_id),
            "deleted_at": datetime.utcnow(),
        })

        assert mongo_conn.flush_deletion_queue() == 0
        # La cola sigue intacta porque no se pudo propagar.
        assert mongo_mock.local_db["DeleteQueue"].count_documents({}) == 1


class TestDoNotResurrect:
    """Tras un borrado en cola, el doc no debe reaparecer al hacer pull."""

    def test_pull_skips_pending_deletions(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        # Estado de partida: ambas BD tienen el doc.
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "fantasma", "usuario_id": USER_ID_STR})
        mongo_mock.remote_db["Tasks"].insert_one({"_id": _id, "contenido": "fantasma", "usuario_id": USER_ID_STR})

        # El usuario borra offline. queue_deletion lo registra en DeleteQueue
        # y elimina la copia local.
        mongo_conn.queue_deletion("Tasks", _id)
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id}) is None

        # Aun sin haber propagado, un pull NO debe traerlo de vuelta.
        mongo_conn.sync_all_collections()
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id}) is None

    def test_flush_then_pull_no_doc_remains(self, mongo_mock, monkeypatch):
        """Caso que SI funciona: con `_id` string en el remoto, flush + pull
        deja todo coherente. Para `_id` ObjectId ver xfail en TestFlushQueue."""
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = "task-string-id-2"
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "x", "usuario_id": USER_ID_STR})
        mongo_mock.remote_db["Tasks"].insert_one({"_id": _id, "contenido": "x", "usuario_id": USER_ID_STR})

        mongo_conn.queue_deletion("Tasks", _id)
        mongo_conn.flush_deletion_queue()
        # Ahora la cola esta vacia y el remoto tampoco lo tiene
        mongo_conn.sync_all_collections()
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id}) is None
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id}) is None
