"""Nodo escritor de documentos (LLM).

Genera contenido con el LLM y lo sube a GridFS como nuevo documento
asociado a un proyecto/objetivo.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO

from langchain_core.messages import SystemMessage

from ai.prompts.doc_writer_prompt import DOC_WRITER_NOTE_PROMPT, DOC_WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.services.session_mutations_state import append_session_mutation
from ai.state import AppState
from database.gridfs_storage import (
    promote_local_file_to_remote,
    upload_stream_to_local_storage,
)
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:50]


def _parse_llm_output(raw: str) -> tuple[str, str]:
    """Separa el titulo y el contenido de la respuesta del LLM.

    Espera que la primera linea sea 'TITULO: <titulo>'.
    Devuelve (titulo, contenido). Si no se encuentra el prefijo,
    devuelve ('documento', raw) como fallback.
    """
    lines = raw.strip().splitlines()
    if lines and lines[0].upper().startswith("TITULO:"):
        title = lines[0][len("TITULO:"):].strip()
        content = "\n".join(lines[1:]).lstrip("\n")
        return title or "documento", content
    return "documento", raw


def _generate_filename(title: str = "") -> str:
    """Genera un nombre de archivo unico a partir del titulo, timestamp y uuid corto."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    slug = _slugify(title) if title else "doc"
    return f"{slug}_{ts}_{short_id}.txt"


def _write_note_node(state: AppState, llm) -> AppState:
    """Extrae el texto de la nota del mensaje del usuario y la añade al proyecto."""
    user_id = state.get("user_id", "")
    project_id = state.get("doc_target_project_id", "")

    if not project_id:
        return {"final_response": "No se pudo identificar el proyecto para agregar la anotación."}

    messages = [SystemMessage(content=DOC_WRITER_NOTE_PROMPT)]
    messages.extend(state.get("messages", []))

    try:
        note_text = (invoke_with_retry(llm, messages, retries=1) or "").strip()
    except LLMInvokeError:
        logger.exception("_write_note_node: error extrayendo texto de nota")
        return {"final_response": "No pude procesar el texto de la anotación en este momento."}

    if not note_text:
        return {"final_response": "No pude identificar el texto de la anotación en tu mensaje."}

    try:
        project = ProjectModel.get_project_by_id(project_id, usuario_id=user_id)
    except Exception:
        logger.exception("_write_note_node: error obteniendo proyecto %s", project_id)
        project = None

    if not project:
        return {"final_response": f"No se encontró el proyecto con ID '{project_id}'."}

    project_title = project.get("titulo") or project_id
    new_note = {
        "_id": uuid.uuid4().hex,
        "text": note_text,
        "created_at": datetime.now(timezone.utc),
    }
    notes = list(project.get("notas") or [])
    notes.append(new_note)

    try:
        ProjectModel.update_project(project_id, {"notas": notes}, usuario_id=user_id)
    except Exception:
        logger.exception("_write_note_node: error actualizando proyecto %s", project_id)
        return {"final_response": "No se pudo guardar la anotación en la base de datos."}

    append_session_mutation(user_id, {
        "action": "created",
        "type": "project_note",
        "id": new_note["_id"],
        "description": f"nota en '{project_title}': {note_text[:80]}",
    })
    return {"final_response": f"Anotación añadida al proyecto **{project_title}**:\n\n> {note_text}"}


def doc_writer_node(state: AppState, llm) -> AppState:
    if state.get("doc_op") == "write_note":
        return _write_note_node(state, llm)

    user_id = state.get("user_id", "")
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

    # ── Separar titulo y contenido ────────────────────────────────
    doc_title, doc_content = _parse_llm_output(generated_text)

    # ── Crear archivo ─────────────────────────────────────────────
    filename = _generate_filename(doc_title)
    file_bytes = doc_content.encode("utf-8")
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
        "description": f"documento generado para proyecto {project_id or 'sin proyecto'}",
    })

    # ── Respuesta final ───────────────────────────────────────────
    parts = [f"Documento generado correctamente: **{doc_title}**\n`{filename}`"]
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
