"""Nodo organizador de operaciones sobre documentos (NO LLM).

Prepara el state para doc_reader o doc_writer usando los valores
ya resueltos por el supervisor (doc_op, doc_read_mode, doc_write_format,
doc_analyze_points, doc_target_id/ids, doc_target_project_id).
"""

import json
import logging
import unicodedata

from database.gridfs_storage import (
    download_file_from_local_storage,
    download_file_from_remote_storage,
)
from model.project_document_model import ProjectDocumentModel
from ai.services.doc_parser import extract_text
from ai.state import AppState

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 15_000


def _normalize(text: str) -> str:
    """Minusculas y sin acentos."""
    text = (text or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _find_document(text: str, user_id: str, project_id: str = None):
    """Busca un documento por nombre en el mensaje. Devuelve (doc, error)."""
    if project_id:
        docs = ProjectDocumentModel.get_by_project(project_id, usuario_id=user_id)
    else:
        docs = ProjectDocumentModel.get_all_documents(usuario_id=user_id)

    if not docs:
        return None, "No se encontraron documentos asociados."

    normalized = _normalize(text)
    matches = []
    for doc in docs:
        name = _normalize(doc.get("original_name") or doc.get("filename") or "")
        name_no_ext = name.rsplit(".", 1)[0] if "." in name else name
        if name_no_ext and name_no_ext in normalized:
            matches.append(doc)
        elif name and name in normalized:
            matches.append(doc)

    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        names = ", ".join(d.get("original_name", "?") for d in matches)
        return None, f"He encontrado varios documentos que coinciden: {names}. Especifica cual."

    if len(docs) == 1:
        return docs[0], None

    names = ", ".join(d.get("original_name", "?") for d in docs[:5])
    extra = f" (y {len(docs) - 5} mas)" if len(docs) > 5 else ""
    return None, f"No pude identificar el documento. Disponibles: {names}{extra}."


def _download_document_bytes(doc: dict) -> bytes | None:
    """Descarga bytes del documento, intentando local primero, remoto despues."""
    local_id = doc.get("local_upload_id")
    if local_id:
        data = download_file_from_local_storage(local_id)
        if data:
            return data

    remote_id = doc.get("upload_id")
    if remote_id:
        data = download_file_from_remote_storage(remote_id)
        if data:
            return data

    return None


def doc_organizer_node(state: AppState) -> AppState:
    """Nodo organizador: prepara contexto para doc_reader o doc_writer usando valores del supervisor."""
    user_id = state.get("user_id", "")
    doc_op = state.get("doc_op", "read")

    # ── NOTE READ ─────────────────────────────────────────────────
    if doc_op == "read_notes":
        context = {}
        try:
            context = json.loads(state.get("context_json") or "{}")
        except Exception:
            pass
        project_id = state.get("doc_target_project_id", "")
        projects = context.get("projects", [])
        project = next((p for p in projects if str(p.get("_id", "")) == project_id), None)
        if not project and len(projects) == 1:
            project = projects[0]
        if not project:
            msg = "No se encontró el proyecto para leer las anotaciones."
            return {"doc_op": "read_notes", "doc_error": msg, "final_response": msg}
        return {
            "doc_op": "read_notes",
            "doc_target_project_id": str(project.get("_id", "")),
            "doc_notes_data": project.get("notas") or [],
        }

    # ── NOTE WRITE ────────────────────────────────────────────────
    if doc_op == "write_note":
        project_id = state.get("doc_target_project_id", "")
        if not project_id:
            msg = "No se pudo identificar el proyecto para agregar la anotación."
            return {"doc_op": "write_note", "doc_error": msg, "final_response": msg}
        return {"doc_op": "write_note", "doc_target_project_id": project_id}

    # ── FILE WRITE ────────────────────────────────────────────────
    if doc_op == "write":
        return {
            "doc_op": "write",
            "doc_write_format": state.get("doc_write_format") or "txt",
            "doc_target_project_id": state.get("doc_target_project_id") or "",
            "doc_target_goal_id": state.get("doc_target_goal_id") or "",
        }

    # ── FILE READ ─────────────────────────────────────────────────
    read_mode = state.get("doc_read_mode") or "full"
    analyze_points = state.get("doc_analyze_points") or ""

    # ── Multi-doc: el supervisor resolvió varios documentos ───────────
    preresolved_ids = state.get("doc_target_ids") or []
    if preresolved_ids:
        contents = []
        loaded_ids = []
        for did in preresolved_ids:
            doc = ProjectDocumentModel.get_document_by_id(did, usuario_id=user_id)
            if not doc:
                logger.warning("doc_organizer: documento %s no encontrado", did)
                continue
            name = doc.get("original_name") or doc.get("filename") or "documento"
            raw_bytes = _download_document_bytes(doc)
            if not raw_bytes:
                contents.append(f"=== {name} ===\n[No se pudo descargar el archivo]\n")
                loaded_ids.append(did)
                continue
            content_type = doc.get("content_type") or ""
            text = extract_text(raw_bytes, content_type, name)
            if len(text) > MAX_CONTENT_CHARS:
                text = text[:MAX_CONTENT_CHARS] + "\n[... contenido truncado ...]"
            contents.append(f"=== {name} ===\n{text}\n")
            loaded_ids.append(did)

        if not contents:
            msg = "No se pudo descargar ninguno de los documentos solicitados."
            return {"doc_error": msg, "final_response": msg}

        return {
            "doc_op": "read",
            "doc_read_mode": read_mode,
            "doc_target_ids": loaded_ids,
            "doc_target_name": f"{len(contents)} documentos",
            "doc_target_project_id": "",
            "doc_content_text": "\n".join(contents),
            "doc_analyze_points": analyze_points,
        }

    # ── Single doc: el supervisor resolvió el documento ──────────
    preresolved_id = state.get("doc_target_id", "")
    if preresolved_id:
        doc = ProjectDocumentModel.get_document_by_id(preresolved_id, usuario_id=user_id)
        if not doc:
            msg = f"No se encontró el documento con ID '{preresolved_id}'."
            return {"doc_error": msg, "final_response": msg}
        project_id = str(doc.get("project_id", ""))
        goal_id = str(doc.get("goal_id", "")) if doc.get("goal_id") else ""
    else:
        # Fallback: buscar documento por nombre en el último mensaje
        user_text = ""
        for msg in reversed(state.get("messages", [])):
            if hasattr(msg, "content") and getattr(msg, "type", None) == "human":
                user_text = (msg.content or "").strip()
                break
        doc, error = _find_document(user_text, user_id)
        if error:
            return {"doc_error": error, "final_response": error}
        project_id = str(doc.get("project_id", ""))
        goal_id = str(doc.get("goal_id", "")) if doc.get("goal_id") else ""

    doc_name = doc.get("original_name") or doc.get("filename") or "documento"
    content_type = doc.get("content_type") or ""

    raw_bytes = _download_document_bytes(doc)
    if not raw_bytes:
        msg = f"No se pudo descargar el archivo '{doc_name}' desde el almacenamiento."
        return {"doc_error": msg, "final_response": msg}

    text_content = extract_text(raw_bytes, content_type, doc_name)

    if len(text_content) > MAX_CONTENT_CHARS:
        text_content = text_content[:MAX_CONTENT_CHARS] + "\n\n[... contenido truncado por longitud ...]"
        if read_mode == "full":
            read_mode = "summary"

    return {
        "doc_op": "read",
        "doc_read_mode": read_mode,
        "doc_target_id": str(doc.get("_id", "")),
        "doc_target_name": doc_name,
        "doc_target_project_id": project_id,
        "doc_target_goal_id": goal_id,
        "doc_content_text": text_content,
        "doc_analyze_points": analyze_points,
    }
