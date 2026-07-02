"""Tests del modelo `ProjectDocumentFolderModel` sobre `mongomock`."""

from __future__ import annotations

import pytest
from bson import ObjectId

from model.project_document_folder_model import ProjectDocumentFolderModel

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _insert_folder(mongo_mock, project_id=None, **extra):
    folder = {
        "_id": ObjectId(),
        "project_id": project_id or ObjectId(),
        "name": "Docs",
        "usuario_id": USER_ID,
        **extra,
    }
    mongo_mock.local_db["ProjectDocumentFolders"].insert_one(folder)
    return folder


class TestQueries:
    def test_get_by_project_objectid(self, mongo_mock):
        pid = ObjectId()
        _insert_folder(mongo_mock, project_id=pid)
        _insert_folder(mongo_mock, project_id=ObjectId())
        assert len(ProjectDocumentFolderModel.get_by_project(pid)) == 1

    def test_get_by_project_string(self, mongo_mock):
        pid = ObjectId()
        _insert_folder(mongo_mock, project_id=pid)
        assert len(ProjectDocumentFolderModel.get_by_project(str(pid))) == 1

    def test_get_folder_by_id(self, mongo_mock):
        folder = _insert_folder(mongo_mock)
        assert ProjectDocumentFolderModel.get_folder_by_id(folder["_id"]) is not None
        assert ProjectDocumentFolderModel.get_folder_by_id(str(folder["_id"])) is not None


class TestMutations:
    def test_insert_converts_project_id_and_sets_defaults(self, mongo_mock):
        pid = str(ObjectId())
        out = ProjectDocumentFolderModel.insert_folder({"project_id": pid, "name": " Material "})
        assert isinstance(out["project_id"], ObjectId)
        assert out["name"] == "Material"
        assert out["usuario_id"]
        assert "created_at" in out

    def test_delete_folder(self, mongo_mock):
        folder = _insert_folder(mongo_mock)
        assert ProjectDocumentFolderModel.delete_folder(folder["_id"]) is True
        assert mongo_mock.local_db["ProjectDocumentFolders"].count_documents({}) == 0
