"""Bateria de `database/gridfs_storage.py` (helpers de subida/descarga/baja)."""

from __future__ import annotations

from io import BytesIO

import pytest
from bson import ObjectId

from database import gridfs_storage


def _stream_for_test(data=b"hola"):
    return BytesIO(data)


class TestGetGridfsBucket:
    def test_none_database_yields_none(self):
        assert gridfs_storage._get_gridfs_bucket(None) is None


class TestUploadStreamToLocal:
    def test_returns_object_id(self, gridfs_patch):
        out = gridfs_storage.upload_stream_to_local_storage(
            _stream_for_test(), original_name="x.txt", content_type="text/plain",
        )
        assert out is not None

    def test_bucket_none_returns_none(self, monkeypatch):
        monkeypatch.setattr(gridfs_storage, "get_local_gridfs_bucket", lambda: None)
        out = gridfs_storage.upload_stream_to_local_storage(
            _stream_for_test(), original_name="x.txt",
        )
        assert out is None

    def test_handles_seek_exception(self, gridfs_patch):
        """Un stream sin seek() no rompe la subida."""
        class _NoSeek:
            def read(self):
                return b"data"
            # Sin seek()

        # Verifica que no levanta excepcion durante la subida
        # (la implementacion captura el fallo del seek silenciosamente)
        try:
            gridfs_storage.upload_stream_to_local_storage(
                _NoSeek(), original_name="x.txt",
            )
        except Exception:
            pytest.fail("upload_stream_to_local_storage no deberia propagar errores de seek")


class TestUploadFileToRemote:
    def test_no_remote_returns_none(self, monkeypatch):
        monkeypatch.setattr(gridfs_storage, "get_remote_gridfs_bucket", lambda app=None: None)
        out = gridfs_storage.upload_file_to_remote_storage("/tmp/x")
        assert out is None

    def test_missing_file_returns_none(self, gridfs_patch, monkeypatch):
        # Existe el bucket remoto pero el path no apunta a un archivo real
        out = gridfs_storage.upload_file_to_remote_storage("/tmp/__no_existe__")
        assert out is None

    def test_uploads_existing_file(self, gridfs_patch, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes(b"contenido")
        out = gridfs_storage.upload_file_to_remote_storage(
            str(f), original_name="doc.txt", content_type="text/plain",
        )
        assert out is not None


class TestDownloadFromStorage:
    def test_local_download_returns_bytes(self, gridfs_patch):
        fid = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"abc"), original_name="x.txt",
        )
        out = gridfs_storage.download_file_from_local_storage(fid)
        assert out == b"abc"

    def test_local_download_with_no_file_id_returns_none(self):
        assert gridfs_storage.download_file_from_local_storage(None) is None
        assert gridfs_storage.download_file_from_local_storage("") is None

    def test_local_download_missing_file(self, gridfs_patch):
        assert gridfs_storage.download_file_from_local_storage(ObjectId()) is None

    def test_local_download_no_bucket(self, monkeypatch):
        monkeypatch.setattr(gridfs_storage, "get_local_gridfs_bucket", lambda: None)
        assert gridfs_storage.download_file_from_local_storage(ObjectId()) is None

    def test_remote_download_with_no_file_id(self):
        assert gridfs_storage.download_file_from_remote_storage(None) is None

    def test_remote_download_no_bucket(self, monkeypatch):
        monkeypatch.setattr(
            gridfs_storage, "get_remote_gridfs_bucket", lambda app=None: None
        )
        assert gridfs_storage.download_file_from_remote_storage(ObjectId()) is None


class TestDeleteFromStorage:
    def test_local_delete_returns_true(self, gridfs_patch):
        fid = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"x"), original_name="x.txt",
        )
        assert gridfs_storage.delete_file_from_local_storage(fid) is True

    def test_local_delete_with_no_id(self):
        assert gridfs_storage.delete_file_from_local_storage(None) is False

    def test_local_delete_no_bucket(self, monkeypatch):
        monkeypatch.setattr(gridfs_storage, "get_local_gridfs_bucket", lambda: None)
        assert gridfs_storage.delete_file_from_local_storage(ObjectId()) is False

    def test_remote_delete_no_bucket(self, monkeypatch):
        monkeypatch.setattr(
            gridfs_storage, "get_remote_gridfs_bucket", lambda app=None: None,
        )
        assert gridfs_storage.delete_file_from_remote_storage(ObjectId()) is False


class TestPromoteLocalToRemote:
    def test_promote_success(self, gridfs_patch):
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"abc"), original_name="x.txt",
        )
        remote_id = gridfs_storage.promote_local_file_to_remote(
            local_id, original_name="x.txt", content_type="text/plain",
        )
        assert remote_id is not None

    def test_promote_without_local_bytes(self, monkeypatch):
        # Si la descarga local devuelve None, no se promueve
        monkeypatch.setattr(gridfs_storage, "download_file_from_local_storage", lambda fid: None)
        out = gridfs_storage.promote_local_file_to_remote(
            ObjectId(), original_name="x.txt",
        )
        assert out is None

    def test_promote_without_remote_bucket(self, gridfs_patch, monkeypatch):
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"x"), original_name="x.txt",
        )
        monkeypatch.setattr(
            gridfs_storage, "get_remote_gridfs_bucket", lambda app=None: None
        )
        out = gridfs_storage.promote_local_file_to_remote(local_id, original_name="x.txt")
        assert out is None
