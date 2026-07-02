"""Bateria del modelo `ProjectDocumentModel` sobre `mongomock`."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.project_document_model import ProjectDocumentModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_doc(mongo_mock, project_id=None, **extra):
    d = {
        "_id": ObjectId(),
        "project_id": project_id or ObjectId(),
        "original_name": "x.txt",
        "usuario_id": USER_ID,
        **extra,
    }
    mongo_mock.local_db["ProjectDocuments"].insert_one(d)
    return d


class TestQueries:
    def test_get_all_documents(self, mongo_mock):
        _insert_doc(mongo_mock)
        _insert_doc(mongo_mock)
        assert len(ProjectDocumentModel.get_all_documents()) == 2

    def test_get_by_project_objectid(self, mongo_mock):
        pid = ObjectId()
        _insert_doc(mongo_mock, project_id=pid)
        _insert_doc(mongo_mock, project_id=ObjectId())
        assert len(ProjectDocumentModel.get_by_project(pid)) == 1

    def test_get_by_project_string(self, mongo_mock):
        pid = ObjectId()
        _insert_doc(mongo_mock, project_id=pid)
        assert len(ProjectDocumentModel.get_by_project(str(pid))) == 1

    def test_get_by_project_none(self, mongo_mock):
        assert ProjectDocumentModel.get_by_project(None) == []

    def test_get_document_by_id(self, mongo_mock):
        d = _insert_doc(mongo_mock)
        assert ProjectDocumentModel.get_document_by_id(d["_id"]) is not None
        assert ProjectDocumentModel.get_document_by_id(str(d["_id"])) is not None


class TestInsertDocument:
    def test_inserts_with_defaults(self, mongo_mock):
        out = ProjectDocumentModel.insert_document({
            "project_id": ObjectId(),
            "original_name": "x.txt",
            "remote_sync_pending": False,
        })
        assert "_id" in out
        assert "uploaded_at" in out
        assert out["usuario_id"]

    def test_insert_with_remote_sync_pending_skips_sync(self, mongo_mock):
        out = ProjectDocumentModel.insert_document({
            "project_id": ObjectId(),
            "original_name": "x.txt",
            "local_upload_id": ObjectId(),
            "remote_sync_pending": True,
        })
        assert out["remote_sync_pending"] is True

    def test_insert_converts_string_project_id_to_oid(self, mongo_mock):
        pid = str(ObjectId())
        out = ProjectDocumentModel.insert_document({
            "project_id": pid,
            "original_name": "x.txt",
        })
        assert isinstance(out["project_id"], ObjectId)

    def test_insert_converts_string_goal_id_to_oid(self, mongo_mock):
        gid = str(ObjectId())
        out = ProjectDocumentModel.insert_document({
            "project_id": ObjectId(),
            "goal_id": gid,
            "original_name": "x.txt",
        })
        assert isinstance(out["goal_id"], ObjectId)

    def test_insert_converts_string_folder_id_to_oid(self, mongo_mock):
        fid = str(ObjectId())
        out = ProjectDocumentModel.insert_document({
            "project_id": ObjectId(),
            "folder_id": fid,
            "original_name": "x.txt",
        })
        assert isinstance(out["folder_id"], ObjectId)


class TestUpdateDocument:
    def test_updates_fields(self, mongo_mock):
        d = _insert_doc(mongo_mock)
        out = ProjectDocumentModel.update_document(d["_id"], {"original_name": "y.txt"})
        assert out["original_name"] == "y.txt"

    def test_update_with_pending_flag_skips_sync(self, mongo_mock):
        d = _insert_doc(mongo_mock, remote_sync_pending=True)
        out = ProjectDocumentModel.update_document(d["_id"], {"original_name": "y"})
        assert out["original_name"] == "y"

    def test_update_with_sync_remote_false(self, mongo_mock):
        d = _insert_doc(mongo_mock)
        out = ProjectDocumentModel.update_document(d["_id"], {"original_name": "y"}, sync_remote=False)
        assert out["original_name"] == "y"

    def test_update_converts_folder_id(self, mongo_mock):
        d = _insert_doc(mongo_mock)
        fid = str(ObjectId())
        out = ProjectDocumentModel.update_document(d["_id"], {"folder_id": fid}, sync_remote=False)
        assert isinstance(out["folder_id"], ObjectId)


class TestPendingRemoteUploads:
    def test_get_pending_only_returns_with_flag_and_local_id(self, mongo_mock):
        # con flag y local_upload_id: incluido
        _insert_doc(mongo_mock, remote_sync_pending=True, local_upload_id=ObjectId())
        # con flag pero sin local_upload_id: excluido
        _insert_doc(mongo_mock, remote_sync_pending=True)
        # sin flag: excluido
        _insert_doc(mongo_mock, local_upload_id=ObjectId())
        out = ProjectDocumentModel.get_pending_remote_uploads()
        assert len(out) == 1

    def test_promote_pending_with_no_pending_returns_zero(self, mongo_mock):
        assert ProjectDocumentModel.promote_pending_remote_uploads() == 0

    def test_promote_pending_handles_failed_upload(self, mongo_mock, monkeypatch, gridfs_patch):
        # documento pendiente
        _insert_doc(mongo_mock, remote_sync_pending=True, local_upload_id=ObjectId())
        # forzar que el helper devuelva None (no promovido)
        from model import project_document_model
        monkeypatch.setattr(
            project_document_model, "promote_local_file_to_remote",
            lambda *a, **k: None,
        )
        assert ProjectDocumentModel.promote_pending_remote_uploads() == 0


class TestDeleteDocument:
    def test_delete_returns_true(self, mongo_mock):
        d = _insert_doc(mongo_mock)
        assert ProjectDocumentModel.delete_document(d["_id"]) is True
        assert mongo_mock.local_db["ProjectDocuments"].count_documents({}) == 0

    def test_delete_with_local_upload_calls_storage(self, mongo_mock, monkeypatch):
        d = _insert_doc(mongo_mock, local_upload_id=ObjectId())
        calls = []
        from model import project_document_model
        monkeypatch.setattr(
            project_document_model, "delete_file_from_local_storage",
            lambda fid: calls.append(("local", fid)) or True,
        )
        ProjectDocumentModel.delete_document(d["_id"])
        assert calls and calls[0][0] == "local"

    def test_delete_with_remote_upload_calls_remote_storage(self, mongo_mock, monkeypatch):
        d = _insert_doc(mongo_mock, upload_id=ObjectId())
        calls = []
        from model import project_document_model
        monkeypatch.setattr(
            project_document_model, "delete_file_from_remote_storage",
            lambda fid: calls.append(("remote", fid)) or True,
        )
        ProjectDocumentModel.delete_document(d["_id"])
        assert calls and calls[0][0] == "remote"

    def test_delete_missing_returns_false(self, mongo_mock):
        assert ProjectDocumentModel.delete_document(ObjectId()) is False
