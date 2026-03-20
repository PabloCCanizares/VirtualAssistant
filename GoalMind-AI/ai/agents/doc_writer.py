"""Nodo escritor de documentos (LLM).

Genera contenido con el LLM y lo sube a GridFS como nuevo documento
asociado a un proyecto/objetivo.
"""

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO

from langchain_core.messages import SystemMessage

from database.gridfs_storage import (
    promote_local_file_to_remote,
    upload_stream_to_local_storage,
)
from model.project_document_model import ProjectDocumentModel
from ai.prompts.doc_writer_prompt import DOC_WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.services.session_mutations_state import append_session_mutation
from ai.state import AppState

logger = logging.getLogger(__name__)


def _generate_pdf_bytes(text: str, title: str = "") -> bytes:
    """Genera un PDF simple a partir de texto plano."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=12)
    if title:
        pdf.set_font("Helvetica", "B", size=16)
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.ln(10)
        pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 7, text)
    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


def _generate_filename(user_text: str, fmt: str) -> str:
    """Genera un nombre de archivo unico basado en timestamp + uuid corto."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    ext = "pdf" if fmt == "pdf" else "txt"
    return f"doc_{ts}_{short_id}.{ext}"


def doc_writer_node(state: AppState, llm) -> AppState:
    user_id = state.get("user_id", "")
    write_format = state.get("doc_write_format", "txt")
    project_id = state.get("doc_target_project_id") or None
    goal_id = state.get("doc_target_goal_id") or None

    # ── Generar contenido con LLM ─────────────────────────────────
    messages = [
        SystemMessage(content=DOC_WRITER_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))

    try:
        generated_text = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("doc_writer_node: error invocando LLM")
        return {"final_response": "No pude generar el documento en este momento."}

    if not generated_text or not generated_text.strip():
        return {"final_response": "El modelo no genero contenido para el documento."}

    # ── Crear archivo ─────────────────────────────────────────────
    filename = _generate_filename("", write_format)

    if write_format == "pdf":
        try:
            file_bytes = _generate_pdf_bytes(generated_text)
            content_type = "application/pdf"
        except Exception:
            logger.exception("doc_writer_node: error generando PDF, fallback a TXT")
            file_bytes = generated_text.encode("utf-8")
            content_type = "text/plain"
            filename = filename.replace(".pdf", ".txt")
    else:
        file_bytes = generated_text.encode("utf-8")
        content_type = "text/plain"

    # ── Subir a GridFS ────────────────────────────────────────────
    stream = BytesIO(file_bytes)
    metadata = {
        "project_id": project_id,
        "goal_id": goal_id,
        "usuario_id": user_id,
        "filename": filename,
    }

    local_upload_id = upload_stream_to_local_storage(
        stream,
        original_name=filename,
        content_type=content_type,
        metadata=metadata,
    )

    if not local_upload_id:
        return {"final_response": "No se pudo guardar el documento en el almacenamiento."}

    # ── Intentar promover a remoto ────────────────────────────────
    remote_upload_id = None
    try:
        remote_upload_id = promote_local_file_to_remote(
            local_upload_id,
            original_name=filename,
            content_type=content_type,
            metadata=metadata,
        )
    except Exception:
        logger.warning("doc_writer_node: no se pudo promover a remoto", exc_info=True)

    # ── Registrar en ProjectDocuments ─────────────────────────────
    doc_data = {
        "project_id": project_id,
        "goal_id": goal_id,
        "filename": filename,
        "original_name": filename,
        "content_type": content_type,
        "size": len(file_bytes),
        "usuario_id": user_id,
    }

    if remote_upload_id:
        doc_data["upload_id"] = remote_upload_id
        doc_data["remote_sync_pending"] = False
    else:
        doc_data["local_upload_id"] = local_upload_id
        doc_data["remote_sync_pending"] = True

    try:
        ProjectDocumentModel.insert_document(doc_data, usuario_id=user_id)
    except Exception:
        logger.exception("doc_writer_node: error insertando documento en BD")
        return {"final_response": "El archivo se creo pero no se pudo registrar en la base de datos."}

    # ── Registrar mutacion de sesion ─────────────────────────────
    doc_id = str(doc_data.get("_id", "") or doc_data.get("upload_id", "") or local_upload_id)
    append_session_mutation(user_id, {
        "action": "created",
        "type": "document",
        "id": doc_id,
        "name": filename,
        "description": f"documento generado ({write_format}) para proyecto {project_id or 'sin proyecto'}",
    })

    # ── Respuesta final ───────────────────────────────────────────
    parts = [f"Documento generado correctamente: **{filename}**"]
    if project_id:
        project_name = ""
        try:
            import json
            ctx = json.loads(state.get("context_json") or "{}")
            for p in ctx.get("projects", []):
                if str(p.get("_id", "")) == str(project_id):
                    project_name = p.get("titulo", "")
                    break
        except Exception:
            pass
        parts.append(f"Proyecto: {project_name or project_id}")
    if goal_id:
        parts.append(f"Objetivo: {goal_id}")

    final_msg = "\n".join(parts)
    return {"final_response": final_msg}
