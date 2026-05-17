"""Tests de integracion sobre la sincronizacion de GridFS para documentos.

GridFS es **unidireccional** local -> remoto: cuando se sube un archivo
estando offline o sin remoto, queda con la bandera `remote_sync_pending=True`
y `local_upload_id` apuntando al bucket local. La metadata correspondiente en
`ProjectDocuments` se EXCLUYE del sync hasta que el binario se promueva al
remoto via `promote_local_file_to_remote`.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from bson import ObjectId

pytestmark = pytest.mark.integration

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"


class TestLocalUploadFlagsPending:
    """Subir a local sin remoto activa `remote_sync_pending=True`."""

    def test_local_upload_when_remote_absent(self, gridfs_patch, no_remote):
        from database.gridfs_storage import upload_stream_to_local_storage

        file_id = upload_stream_to_local_storage(
            BytesIO(b"binary content"),
            original_name="x.txt",
            content_type="text/plain",
        )
        assert file_id is not None
        # El binario quedo en el bucket local de mentira
        assert gridfs_patch.local.files[file_id][0] == b"binary content"
        # Y el bucket remoto sigue vacio
        assert len(gridfs_patch.remote.files) == 0


class TestSyncSkipsPending:
    """`sync_local_to_remote` no sube metadata pendiente."""

    def test_pending_remote_sync_doc_is_skipped(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        meta_id = ObjectId()
        local_upload_id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": meta_id,
            "usuario_id": USER_ID_STR,
            "project_id": ObjectId(),
            "original_name": "x.txt",
            "content_type": "text/plain",
            "size": 14,
            "local_upload_id": local_upload_id,
            "remote_sync_pending": True,
        })

        mongo_conn.sync_local_to_remote()
        # Metadata NO subida al remoto.
        assert mongo_mock.remote_db["ProjectDocuments"].find_one({"_id": meta_id}) is None

    def test_promoted_doc_can_be_pushed(self, mongo_mock, monkeypatch, gridfs_patch):
        """Una vez se promueve a remoto el binario y se baja el flag,
        la metadata se sube en el siguiente push (y sin `local_upload_id`)."""
        from database import gridfs_storage, mongo_conn

        monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda app=None: True)

        # 1) Sube binario al bucket local
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"contenido"),
            original_name="x.txt",
            content_type="text/plain",
        )

        # 2) Registra la metadata con flag pendiente
        meta_id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": meta_id,
            "usuario_id": USER_ID_STR,
            "original_name": "x.txt",
            "local_upload_id": local_id,
            "remote_sync_pending": True,
        })

        # 3) Promueve el binario a remoto
        remote_id = gridfs_storage.promote_local_file_to_remote(
            local_id,
            original_name="x.txt",
            content_type="text/plain",
        )
        assert remote_id is not None
        # El binario aparece en el remoto
        assert any(name == "x.txt" for _, name, _ in gridfs_patch.remote.files.values())

        # 4) Baja la bandera y referencia al upload remoto
        mongo_mock.local_db["ProjectDocuments"].update_one(
            {"_id": meta_id},
            {"$set": {"remote_sync_pending": False, "upload_id": remote_id}},
        )

        # 5) Push: ahora se sube la metadata, sin `local_upload_id`
        mongo_conn.sync_local_to_remote()
        remote_meta = mongo_mock.remote_db["ProjectDocuments"].find_one({"_id": meta_id})
        assert remote_meta is not None
        assert "local_upload_id" not in remote_meta
        assert remote_meta["upload_id"] == remote_id


class TestUnidirectionalLocalToRemote:
    """No existe pull de binarios desde remoto a local en estos tests."""

    def test_promote_copies_bytes_from_local_to_remote(self, gridfs_patch):
        from database.gridfs_storage import (
            promote_local_file_to_remote,
            upload_stream_to_local_storage,
        )

        local_id = upload_stream_to_local_storage(
            BytesIO(b"abc-DEF-123"),
            original_name="data.bin",
            content_type="application/octet-stream",
        )

        remote_id = promote_local_file_to_remote(
            local_id,
            original_name="data.bin",
            content_type="application/octet-stream",
        )
        assert remote_id is not None
        # El contenido es identico
        assert gridfs_patch.local.files[local_id][0] == b"abc-DEF-123"
        assert gridfs_patch.remote.files[remote_id][0] == b"abc-DEF-123"

    def test_promote_without_remote_returns_none(self, gridfs_patch, no_remote):
        from database.gridfs_storage import (
            promote_local_file_to_remote,
            upload_stream_to_local_storage,
        )

        local_id = upload_stream_to_local_storage(
            BytesIO(b"data"),
            original_name="data.bin",
        )
        assert promote_local_file_to_remote(local_id, original_name="data.bin") is None
