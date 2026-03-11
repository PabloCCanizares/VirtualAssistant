from io import BytesIO

from flask import Flask

import controllers.project_controller as project_controller
from model.project_document_model import ProjectDocumentModel


def test_resolve_document_source_uses_remote_when_local_missing(monkeypatch):
    monkeypatch.setattr(
        project_controller,
        "download_file_from_remote_storage",
        lambda upload_id, app=None: b"remote-bytes",
    )

    app = Flask(__name__)
    with app.app_context():
        file_path, file_stream, error = project_controller._resolve_document_source(
            {
                "local_path": "missing-file.txt",
                "upload_id": "67efbbbbbbbbbbbbbbbb0001",
                "original_name": "demo.txt",
            }
        )

    assert file_path is None
    assert isinstance(file_stream, BytesIO)
    assert file_stream.read() == b"remote-bytes"
    assert error is None


def test_delete_document_removes_remote_upload(monkeypatch):
    calls = []

    class FakeLocalCollection:
        def find_one(self, query):
            return {"_id": query["_id"], "upload_id": "67efbbbbbbbbbbbbbbbb0002"}

        def delete_one(self, query):
            calls.append(("local_delete", query["_id"]))

            class Result:
                deleted_count = 1

            return Result()

    class FakeRemoteCollection:
        def delete_one(self, query):
            calls.append(("remote_delete", query["_id"]))

    monkeypatch.setattr(
        "model.project_document_model.get_collection",
        lambda name: (FakeLocalCollection(), FakeRemoteCollection()),
    )
    monkeypatch.setattr(
        "model.project_document_model.delete_file_from_remote_storage",
        lambda upload_id, app=None: calls.append(("remote_file_delete", upload_id)) or True,
    )

    assert ProjectDocumentModel.delete_document("67efbbbbbbbbbbbbbbbb0003") is True
    assert ("remote_file_delete", "67efbbbbbbbbbbbbbbbb0002") in calls
