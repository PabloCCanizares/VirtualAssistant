"""Tests del servicio `doc_summarize_service.summarize_and_save_note`."""

from __future__ import annotations

from io import BytesIO

import pytest
from bson import ObjectId

from ai.services import doc_summarize_service
from ai.services.doc_summarize_service import summarize_and_save_note
from tests._fakes import ScriptedLLM


@pytest.fixture
def patch_summarize_llm(monkeypatch):
    """Sustituye `build_llm` en el namespace de `doc_summarize_service`.

    Necesario porque el servicio hace `from ai.config import build_llm`, lo que
    crea una referencia local al objeto. Cambiar `ai.config.build_llm` ya no
    afecta a la referencia que ve el servicio.
    """

    def _patch(llm_instance):
        monkeypatch.setattr(doc_summarize_service, "build_llm", lambda model=None: llm_instance)
        return llm_instance

    return _patch

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def _seed_project_and_doc(mongo_mock, gridfs_patch, *, with_local=True):
    pid = ObjectId()
    mongo_mock.local_db["Projects"].insert_one({
        "_id": pid, "titulo": "P", "usuario_id": USER_ID, "notas": [],
    })
    from database import gridfs_storage
    local_id = None
    if with_local:
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"contenido textual"),
            original_name="x.txt",
            content_type="text/plain",
        )
    doc_id = ObjectId()
    doc = {
        "_id": doc_id,
        "project_id": pid,
        "original_name": "x.txt",
        "content_type": "text/plain",
        "usuario_id": USER_ID,
    }
    if local_id is not None:
        doc["local_upload_id"] = local_id
    mongo_mock.local_db["ProjectDocuments"].insert_one(doc)
    return pid, doc_id


class TestSummarizeAndSaveNote:
    def test_full_flow_creates_note(self, mongo_mock, gridfs_patch, patch_summarize_llm):
        pid, doc_id = _seed_project_and_doc(mongo_mock, gridfs_patch)
        llm = ScriptedLLM({"resumen conciso y estructurado": "Resumen del documento."})
        patch_summarize_llm(llm)
        msg = summarize_and_save_note(str(doc_id), str(pid))
        assert "nota" in msg.lower()
        project = mongo_mock.local_db["Projects"].find_one({"_id": pid})
        notas = project.get("notas") or []
        assert len(notas) == 1
        assert "Resumen del documento" in notas[0]["text"]

    def test_document_not_found_raises_value_error(self):
        with pytest.raises(ValueError, match="Documento no encontrado"):
            summarize_and_save_note(str(ObjectId()), str(ObjectId()))

    def test_project_not_found_raises_value_error(
        self, mongo_mock, gridfs_patch, patch_summarize_llm
    ):
        # Documento sin proyecto referenciado en BD
        from database import gridfs_storage
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"x"), original_name="y.txt", content_type="text/plain",
        )
        doc_id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": doc_id, "original_name": "y.txt",
            "local_upload_id": local_id, "usuario_id": USER_ID,
            "project_id": ObjectId(),
        })
        llm = ScriptedLLM({"resumen conciso y estructurado": "Resumen"})
        patch_summarize_llm(llm)
        # El project_id que pasamos no existe
        with pytest.raises(ValueError, match="Proyecto no encontrado"):
            summarize_and_save_note(str(doc_id), str(ObjectId()))

    def test_no_bytes_raises_runtime_error(
        self, mongo_mock, gridfs_patch, patch_summarize_llm, monkeypatch
    ):
        pid, doc_id = _seed_project_and_doc(mongo_mock, gridfs_patch, with_local=False)
        with pytest.raises(RuntimeError, match="No se pudo descargar"):
            summarize_and_save_note(str(doc_id), str(pid))

    def test_empty_summary_raises_runtime_error(
        self, mongo_mock, gridfs_patch, patch_summarize_llm
    ):
        pid, doc_id = _seed_project_and_doc(mongo_mock, gridfs_patch)
        llm = ScriptedLLM({"resumen conciso y estructurado": "   "})
        patch_summarize_llm(llm)
        with pytest.raises(RuntimeError, match="no gener"):
            summarize_and_save_note(str(doc_id), str(pid))
