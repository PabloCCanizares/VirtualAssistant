"""Tests de integracion sobre `sync_all_collections` (pull) y
`sync_local_to_remote` (push), incluyendo la regla de resolucion de
conflictos por timestamp y el caso de empate.

Reglas verificadas (ver `_remote_should_replace_local` en `mongo_conn`):
- Local vacio -> el doc remoto se descarga (pull).
- Remoto vacio -> el doc local se sube via upsert (push).
- Timestamps distintos -> gana el lado mas reciente.
- Empate sin timestamps con contenido distinto -> gana remoto.
- Todas las escrituras hacia remoto van por upsert (`ReplaceOne(upsert=True)`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from bson import ObjectId

pytestmark = pytest.mark.integration

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"
USER_ID_OID = ObjectId(USER_ID_STR)


def _make_task(_id, contenido, *, updated_at=None, usuario_id=USER_ID_STR):
    doc = {
        "_id": _id,
        "usuario_id": usuario_id,
        "contenido": contenido,
    }
    if updated_at is not None:
        doc["updated_at"] = updated_at
    return doc


class TestPullFromRemote:
    """`sync_all_collections` descarga del remoto al local."""

    def test_pull_brings_remote_only_doc_to_local(
        self, mongo_mock, online, monkeypatch
    ):
        from database.mongo_conn import sync_all_collections
        # `sync_all_collections` usa `from flask import current_app`. Para
        # evitar el `RuntimeError: Working outside of application context`
        # falsificamos `ensure_remote_connection`.
        import database.mongo_conn as mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        remote_id = ObjectId()
        mongo_mock.remote_db["Tasks"].insert_one(
            _make_task(remote_id, "solo en remoto", usuario_id=USER_ID_STR)
        )

        pulled = sync_all_collections()
        assert pulled == 1
        assert mongo_mock.local_db["Tasks"].find_one({"_id": remote_id})["contenido"] == "solo en remoto"

    def test_pull_skips_pending_deletions(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        remote_id = ObjectId()
        mongo_mock.remote_db["Tasks"].insert_one(
            _make_task(remote_id, "marcada para borrar", usuario_id=USER_ID_STR)
        )
        # Marcamos esa task en DeleteQueue para que el pull la ignore.
        mongo_mock.local_db["DeleteQueue"].insert_one({
            "_id": f"Tasks:{remote_id}",
            "collection": "Tasks",
            "target_id": str(remote_id),
            "deleted_at": datetime.utcnow(),
        })

        pulled = mongo_conn.sync_all_collections()
        assert pulled == 0
        assert mongo_mock.local_db["Tasks"].find_one({"_id": remote_id}) is None

    def test_pull_resolves_conflict_by_timestamp_remote_newer(
        self, mongo_mock, monkeypatch
    ):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        now = datetime.utcnow()
        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(
            _make_task(_id, "version local vieja", updated_at=now - timedelta(hours=1))
        )
        mongo_mock.remote_db["Tasks"].insert_one(
            _make_task(_id, "version remota nueva", updated_at=now)
        )

        mongo_conn.sync_all_collections()
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id})["contenido"] == "version remota nueva"

    def test_pull_keeps_local_when_local_is_newer(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        now = datetime.utcnow()
        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(
            _make_task(_id, "local mas nuevo", updated_at=now)
        )
        mongo_mock.remote_db["Tasks"].insert_one(
            _make_task(_id, "remoto viejo", updated_at=now - timedelta(hours=1))
        )

        mongo_conn.sync_all_collections()
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id})["contenido"] == "local mas nuevo"

    def test_tie_without_timestamp_remote_wins(self, mongo_mock, monkeypatch):
        """Empate sin timestamp en ningun lado: gana remoto."""
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        # Sin updated_at en ninguno
        mongo_mock.local_db["Tasks"].insert_one({"_id": _id, "contenido": "local", "usuario_id": USER_ID_STR})
        mongo_mock.remote_db["Tasks"].insert_one({"_id": _id, "contenido": "remoto", "usuario_id": USER_ID_STR})

        mongo_conn.sync_all_collections()
        assert mongo_mock.local_db["Tasks"].find_one({"_id": _id})["contenido"] == "remoto"


class TestPushToRemote:
    """`sync_local_to_remote` sube via upsert los documentos solo locales."""

    def test_push_inserts_local_only_doc_via_upsert(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(_make_task(_id, "subir"))

        pushed = mongo_conn.sync_local_to_remote()
        assert pushed >= 1
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id})["contenido"] == "subir"

    def test_push_does_not_overwrite_newer_remote(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        now = datetime.utcnow()
        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(
            _make_task(_id, "version local vieja", updated_at=now - timedelta(hours=2))
        )
        mongo_mock.remote_db["Tasks"].insert_one(
            _make_task(_id, "version remota nueva", updated_at=now)
        )

        mongo_conn.sync_local_to_remote()
        # El push se debe haber abstenido porque remoto era mas nuevo.
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id})["contenido"] == "version remota nueva"

    def test_push_skips_docs_pending_local_deletion(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(_make_task(_id, "ya borrada local"))
        mongo_mock.local_db["DeleteQueue"].insert_one({
            "_id": f"Tasks:{_id}",
            "collection": "Tasks",
            "target_id": str(_id),
            "deleted_at": datetime.utcnow(),
        })

        mongo_conn.sync_local_to_remote()
        assert mongo_mock.remote_db["Tasks"].find_one({"_id": _id}) is None

    def test_push_skips_project_documents_with_pending_remote_sync(self, mongo_mock, monkeypatch):
        """`ProjectDocuments` con `remote_sync_pending=True` no se suben aun."""
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        _id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": _id,
            "usuario_id": USER_ID_STR,
            "original_name": "doc.txt",
            "remote_sync_pending": True,
            "local_upload_id": ObjectId(),
        })

        mongo_conn.sync_local_to_remote()
        assert mongo_mock.remote_db["ProjectDocuments"].find_one({"_id": _id}) is None


class TestPullThenPushOrder:
    """El orden pull-then-push converge: tras correr ambos, las dos BD coinciden."""

    def test_full_cycle_brings_databases_to_same_state(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        # Local tiene un doc unico, remoto tiene otro unico.
        local_id, remote_id = ObjectId(), ObjectId()
        mongo_mock.local_db["Tasks"].insert_one(_make_task(local_id, "solo local"))
        mongo_mock.remote_db["Tasks"].insert_one(_make_task(remote_id, "solo remoto"))

        # Orden pull-then-push
        mongo_conn.sync_all_collections()
        mongo_conn.sync_local_to_remote()

        # Tras ambas pasadas, los dos lados tienen ambos docs.
        for db in (mongo_mock.local_db, mongo_mock.remote_db):
            ids = {d["_id"] for d in db["Tasks"].find()}
            assert local_id in ids
            assert remote_id in ids
