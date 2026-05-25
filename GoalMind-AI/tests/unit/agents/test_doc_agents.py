"""Bateria de los agentes documentales: `doc_organizer`, `doc_reader`, `doc_writer`."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from bson import ObjectId
from langchain_core.messages import HumanMessage

from ai.agents.doc_organizer import doc_organizer_node, _normalize, _find_document
from ai.agents.doc_reader import doc_reader_node
from ai.agents.doc_writer import (
    _generate_filename,
    _parse_llm_output,
    _slugify,
    doc_writer_node,
)
from tests._fakes import ScriptedLLM

pytestmark = pytest.mark.usefixtures("mongo_mock")

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


# ---------------------------------------------------------------------------
# doc_organizer
# ---------------------------------------------------------------------------


class TestDocOrganizerHelpers:
    def test_normalize_removes_accents_and_lowercases(self):
        assert _normalize("Memória Técnica") == "memoria tecnica"

    def test_normalize_empty_returns_empty(self):
        assert _normalize("") == ""


class TestDocOrganizerWriteOps:
    def test_write_file_returns_target_project(self, mongo_mock):
        pid = ObjectId()
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "write",
            "doc_target_project_id": str(pid),
        })
        assert out["doc_op"] == "write"
        assert out["doc_target_project_id"] == str(pid)

    def test_write_note_with_project(self, mongo_mock):
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "write_note",
            "doc_target_project_id": str(ObjectId()),
        })
        assert out["doc_op"] == "write_note"

    def test_write_note_without_project_yields_error(self):
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "write_note",
            "doc_target_project_id": "",
        })
        assert "doc_error" in out

    def test_read_notes_returns_project_notas(self):
        pid = ObjectId()
        context = {"projects": [{"_id": str(pid), "notas": [{"text": "n1"}]}]}
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "read_notes",
            "doc_target_project_id": str(pid),
            "context_json": json.dumps(context),
        })
        assert out["doc_notes_data"] == [{"text": "n1"}]

    def test_read_notes_no_project_yields_error(self):
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "read_notes",
            "doc_target_project_id": "",
            "context_json": "{}",
        })
        assert "doc_error" in out


class TestDocOrganizerReadOps:
    def test_read_preresolved_doc_id(self, mongo_mock, gridfs_patch):
        from database import gridfs_storage
        local_id = gridfs_storage.upload_stream_to_local_storage(
            BytesIO(b"contenido del documento"),
            original_name="x.txt",
            content_type="text/plain",
        )
        doc_id = ObjectId()
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": doc_id,
            "project_id": ObjectId(),
            "original_name": "x.txt",
            "content_type": "text/plain",
            "local_upload_id": local_id,
            "usuario_id": USER_ID,
        })
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": str(doc_id),
            "doc_read_mode": "summary",
        })
        assert "doc_content_text" in out
        assert "contenido" in out["doc_content_text"]

    def test_read_doc_not_found(self, mongo_mock):
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": str(ObjectId()),
        })
        assert "doc_error" in out

    def test_read_multiple_docs(self, mongo_mock, gridfs_patch):
        from database import gridfs_storage
        ids = []
        for i in range(2):
            local_id = gridfs_storage.upload_stream_to_local_storage(
                BytesIO(f"texto {i}".encode()),
                original_name=f"x{i}.txt",
                content_type="text/plain",
            )
            doc_id = ObjectId()
            ids.append(str(doc_id))
            mongo_mock.local_db["ProjectDocuments"].insert_one({
                "_id": doc_id,
                "project_id": ObjectId(),
                "original_name": f"x{i}.txt",
                "content_type": "text/plain",
                "local_upload_id": local_id,
                "usuario_id": USER_ID,
            })
        out = doc_organizer_node({
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_ids": ids,
        })
        assert "2 documentos" in out["doc_target_name"]


class TestFindDocument:
    def test_no_docs_yields_error(self, mongo_mock):
        out, err = _find_document("buscar", USER_ID, project_id=str(ObjectId()))
        assert out is None
        assert err is not None

    def test_finds_single_match(self, mongo_mock):
        mongo_mock.local_db["ProjectDocuments"].insert_one({
            "_id": ObjectId(),
            "original_name": "memoria.pdf",
            "usuario_id": USER_ID,
        })
        out, err = _find_document("resume la memoria", USER_ID)
        assert out is not None
        assert err is None


# ---------------------------------------------------------------------------
# doc_reader (summary, analyze, full y notas)
# ---------------------------------------------------------------------------


class TestDocReader:
    def test_full_mode(self, mongo_mock):
        llm = ScriptedLLM({"agente de lectura de documentos": "Lectura completa"})
        out = doc_reader_node({
            "messages": [HumanMessage(content="x")],
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": "id",
            "doc_target_name": "doc.txt",
            "doc_content_text": "contenido del doc",
            "doc_read_mode": "full",
        }, llm)
        assert "draft_response" in out

    def test_summary_mode(self, mongo_mock):
        llm = ScriptedLLM({"resumen conciso y estructurado": "Resumen"})
        out = doc_reader_node({
            "messages": [HumanMessage(content="x")],
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": "id",
            "doc_target_name": "doc.txt",
            "doc_content_text": "contenido",
            "doc_read_mode": "summary",
        }, llm)
        assert "Resumen" in out["draft_response"]

    def test_analyze_mode_with_points(self, mongo_mock):
        llm = ScriptedLLM({"analizar los aspectos especificos": "Analisis"})
        out = doc_reader_node({
            "messages": [HumanMessage(content="x")],
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": "id",
            "doc_target_name": "doc.txt",
            "doc_content_text": "contenido",
            "doc_read_mode": "analyze",
            "doc_analyze_points": "riesgos tecnicos",
        }, llm)
        assert "Analisis" in out["draft_response"]

    def test_empty_content(self, mongo_mock):
        out = doc_reader_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": "id",
            "doc_target_name": "doc.txt",
            "doc_content_text": "",
            "doc_read_mode": "full",
        }, None)
        assert "No hay contenido" in out["draft_response"]

    def test_read_notes_with_notes(self, mongo_mock):
        llm = ScriptedLLM({"agente de lectura de GoalMind AI": "Notas listadas"})
        out = doc_reader_node({
            "messages": [HumanMessage(content="x")],
            "user_id": USER_ID,
            "doc_op": "read_notes",
            "doc_target_project_id": "p1",
            "doc_notes_data": [{"text": "nota 1", "created_at": "2026-01-01"}],
        }, llm)
        assert "Notas" in out["draft_response"]

    def test_read_notes_empty(self, mongo_mock):
        llm = ScriptedLLM({"agente de lectura de GoalMind AI": "Sin notas"})
        out = doc_reader_node({
            "messages": [HumanMessage(content="x")],
            "user_id": USER_ID,
            "doc_op": "read_notes",
            "doc_target_project_id": "p1",
            "doc_notes_data": [],
        }, llm)
        assert "draft_response" in out

    def test_llm_exception_yields_fallback(self, mongo_mock):
        llm = ScriptedLLM({"agente de lectura de documentos": RuntimeError("LLM")})
        out = doc_reader_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "read",
            "doc_target_id": "id",
            "doc_target_name": "doc.txt",
            "doc_content_text": "x",
            "doc_read_mode": "full",
        }, llm)
        assert "No pude procesar" in out["draft_response"]


# ---------------------------------------------------------------------------
# doc_writer (write file + write_note)
# ---------------------------------------------------------------------------


class TestDocWriterHelpers:
    def test_slugify_strips_special(self):
        assert _slugify("Plan de TRABAJO!") == "plan_de_trabajo"

    def test_slugify_long_titles_truncated(self):
        out = _slugify("a" * 200)
        assert len(out) <= 50

    def test_parse_llm_output_with_titulo(self):
        title, content = _parse_llm_output("TITULO: Plan\n\ncuerpo del doc")
        assert title == "Plan"
        assert content == "cuerpo del doc"

    def test_parse_llm_output_without_titulo(self):
        title, content = _parse_llm_output("solo cuerpo")
        assert title == "documento"
        assert content == "solo cuerpo"

    def test_generate_filename_includes_timestamp(self):
        out = _generate_filename("titulo de ejemplo")
        assert out.endswith(".txt")
        assert "titulo_de_ejemplo" in out


class TestDocWriterNode:
    def test_write_file_flow(self, mongo_mock, gridfs_patch, monkeypatch):
        # LLM devuelve titulo + contenido
        llm = ScriptedLLM({
            "agente de generacion de documentos": "TITULO: Plan\n\nContenido del plan."
        })
        pid = ObjectId()
        out = doc_writer_node({
            "messages": [HumanMessage(content="crea un doc")],
            "user_id": USER_ID,
            "doc_op": "write",
            "doc_target_project_id": str(pid),
            "context_json": "{}",
        }, llm)
        assert "final_response" in out
        assert "Plan" in out["final_response"]
        # Se creo el documento de metadata
        assert mongo_mock.local_db["ProjectDocuments"].count_documents({}) == 1

    def test_write_file_with_empty_content(self, mongo_mock):
        llm = ScriptedLLM({"agente de generacion de documentos": "   "})
        out = doc_writer_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "write",
            "context_json": "{}",
        }, llm)
        assert "no genero contenido" in out["final_response"]

    def test_write_file_with_llm_exception(self, mongo_mock):
        llm = ScriptedLLM({"agente de generacion de documentos": RuntimeError("LLM")})
        out = doc_writer_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "write",
            "context_json": "{}",
        }, llm)
        assert "No pude generar" in out["final_response"]

    def test_write_note_no_project(self, mongo_mock):
        out = doc_writer_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "write_note",
            "doc_target_project_id": "",
        }, None)
        assert "No se pudo identificar" in out["final_response"]

    def test_write_note_empty_text(self, mongo_mock):
        pid = ObjectId()
        mongo_mock.local_db["Projects"].insert_one({"_id": pid, "titulo": "P", "usuario_id": USER_ID})
        llm = ScriptedLLM({"agente de anotaciones": "   "})
        out = doc_writer_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "write_note",
            "doc_target_project_id": str(pid),
        }, llm)
        assert "No pude identificar el texto" in out["final_response"]

    def test_write_note_project_not_found(self, mongo_mock):
        llm = ScriptedLLM({"agente de anotaciones": "mi nota"})
        out = doc_writer_node({
            "messages": [],
            "user_id": USER_ID,
            "doc_op": "write_note",
            "doc_target_project_id": str(ObjectId()),
        }, llm)
        assert "No se encontr" in out["final_response"]  # acepta acentos
