from io import BytesIO
from types import SimpleNamespace

from bson import ObjectId

from services.project_document_service import (
    delete_project_document,
    get_project_document_source,
    upload_project_document,
)

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


class _ProjectModel:
    @staticmethod
    def get_project_by_id(project_id, usuario_id=None):
        return {"_id": project_id, "titulo": "P"}


class _MissingProjectModel:
    @staticmethod
    def get_project_by_id(project_id, usuario_id=None):
        return None


class _DocumentModel:
    inserted = None
    doc = None

    @classmethod
    def insert_document(cls, doc_data, usuario_id=None):
        cls.inserted = dict(doc_data)
        cls.inserted["usuario_id"] = usuario_id
        return cls.inserted

    @classmethod
    def get_document_by_id(cls, doc_id, usuario_id=None):
        return cls.doc

    @classmethod
    def delete_document(cls, doc_id, usuario_id=None):
        return True


def _file(name="x.txt", data=b"abc", mimetype="text/plain"):
    return SimpleNamespace(filename=name, stream=BytesIO(data), mimetype=mimetype)


class TestUploadProjectDocument:
    def test_missing_project_returns_list_redirect(self):
        result = upload_project_document(
            ObjectId(),
            _file(),
            usuario_id=USER_ID,
            project_model=_MissingProjectModel,
            document_model=_DocumentModel,
        )

        assert result.ok is False
        assert result.redirect_to_list is True
        assert result.message == "Proyecto no encontrado."

    def test_remote_promotion_marks_document_synced(self):
        local_id = ObjectId()
        remote_id = ObjectId()

        result = upload_project_document(
            ObjectId(),
            _file(data=b"abcdef"),
            usuario_id=USER_ID,
            project_model=_ProjectModel,
            document_model=_DocumentModel,
            upload_local_fn=lambda *a, **k: local_id,
            promote_remote_fn=lambda *a, **k: remote_id,
        )

        assert result.ok is True
        assert result.document["local_upload_id"] == local_id
        assert result.document["upload_id"] == remote_id
        assert result.document["remote_sync_pending"] is False
        assert result.document["size"] == 6

    def test_remote_absent_keeps_pending_flag(self):
        local_id = ObjectId()

        result = upload_project_document(
            ObjectId(),
            _file(),
            usuario_id=USER_ID,
            project_model=_ProjectModel,
            document_model=_DocumentModel,
            upload_local_fn=lambda *a, **k: local_id,
            promote_remote_fn=lambda *a, **k: None,
        )

        assert result.ok is True
        assert result.document["local_upload_id"] == local_id
        assert "upload_id" not in result.document
        assert result.document["remote_sync_pending"] is True


class TestProjectDocumentSource:
    def test_get_document_source_returns_local_bytes(self):
        doc = {"_id": ObjectId(), "local_upload_id": ObjectId(), "project_id": ObjectId()}
        _DocumentModel.doc = doc

        result = get_project_document_source(
            ObjectId(),
            usuario_id=USER_ID,
            document_model=_DocumentModel,
            download_local_fn=lambda fid: b"local",
            download_remote_fn=lambda fid, app=None: None,
        )

        assert result.ok is True
        assert result.file_bytes == b"local"

    def test_get_document_source_not_found_redirects_to_list(self):
        _DocumentModel.doc = None

        result = get_project_document_source(
            ObjectId(),
            usuario_id=USER_ID,
            document_model=_DocumentModel,
        )

        assert result.ok is False
        assert result.redirect_to_list is True


class TestDeleteProjectDocument:
    def test_delete_queues_and_flushes(self):
        doc_id = ObjectId()
        project_id = ObjectId()
        _DocumentModel.doc = {"_id": doc_id, "project_id": project_id}
        calls = []

        result = delete_project_document(
            doc_id,
            usuario_id=USER_ID,
            document_model=_DocumentModel,
            queue_delete_fn=lambda col, did: calls.append(("queue", col, did)),
            flush_deletion_queue_fn=lambda: calls.append(("flush",)),
        )

        assert result.ok is True
        assert result.project_id == project_id
        assert calls == [("queue", "ProjectDocuments", doc_id), ("flush",)]
