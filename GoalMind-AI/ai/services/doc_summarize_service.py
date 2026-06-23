"""Servicio para resumir un documento y guardar el resumen como nota de proyecto."""

import logging
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from ai.agents.doc_reader import doc_reader_node
from ai.config import build_llm, get_settings
from ai.services.doc_parser import extract_text
from database.gridfs_storage import (
    download_file_from_local_storage,
    download_file_from_remote_storage,
)
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from services.user_context import current_user_id

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 15_000


def summarize_and_save_note(doc_id: str, project_id: str) -> str:
    """
    Resume el documento `doc_id` con el LLM configurado y guarda el resultado
    como nota en el proyecto `project_id`.

    Returns:
        Mensaje de confirmación.

    Raises:
        ValueError: si el documento o el proyecto no se encuentran.
        RuntimeError: si falla la descarga, la extracción o el LLM.
    """
    settings = get_settings()
    user_id = settings.default_user_id or current_user_id()

    # 1. Resolver modelo LLM
    if settings.llm_provider == "gemini":
        model = settings.gemini_model
    elif settings.llm_provider == "groq":
        model = settings.groq_model
    else:
        model = settings.openai_model

    llm = build_llm(model)

    # 2. Obtener metadatos del documento
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=user_id)
    if not doc:
        raise ValueError(f"Documento no encontrado (id={doc_id})")

    doc_name = doc.get("original_name") or doc.get("filename") or "documento"
    content_type = doc.get("content_type", "")

    # 3. Descargar bytes (local primero, remoto como fallback)
    raw_bytes = None
    local_id = doc.get("local_upload_id")
    if local_id:
        raw_bytes = download_file_from_local_storage(local_id)
    if not raw_bytes:
        remote_id = doc.get("upload_id")
        if remote_id:
            raw_bytes = download_file_from_remote_storage(remote_id)

    if not raw_bytes:
        raise RuntimeError(f"No se pudo descargar el documento '{doc_name}'")

    # 4. Extraer texto
    text_content = extract_text(raw_bytes, content_type, doc_name)[:MAX_CONTENT_CHARS]

    # 5. Llamar a doc_reader_node en modo summary
    state = {
        "messages": [HumanMessage(content=f"Resume el documento '{doc_name}'")],
        "user_id": user_id,
        "doc_op": "read",
        "doc_read_mode": "summary",
        "doc_target_id": str(doc.get("_id", "")),
        "doc_target_name": doc_name,
        "doc_content_text": text_content,
        "doc_target_project_id": project_id,
    }

    result = doc_reader_node(state, llm)
    summary_text = (result.get("draft_response") or "").strip()

    if not summary_text:
        raise RuntimeError("El nodo de lectura no generó un resumen")

    # 6. Obtener proyecto y añadir nota con el resumen
    project = ProjectModel.get_project_by_id(project_id, usuario_id=user_id)
    if not project:
        raise ValueError(f"Proyecto no encontrado (id={project_id})")

    note_text = f"[Resumen automático de '{doc_name}']\n\n{summary_text}"
    new_note = {
        "_id": uuid.uuid4().hex,
        "text": note_text,
        "created_at": datetime.now(timezone.utc),
    }
    notes = list(project.get("notas") or [])
    notes.append(new_note)
    ProjectModel.update_project(project_id, {"notas": notes}, usuario_id=user_id)

    return f"Resumen de '{doc_name}' guardado como nota en el proyecto."
