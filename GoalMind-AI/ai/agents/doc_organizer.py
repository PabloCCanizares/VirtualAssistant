"""Nodo organizador de operaciones sobre documentos (NO LLM).

Determina si la operacion es READ o WRITE, identifica el documento
o proyecto/objetivo asociado, y prepara el state para doc_reader o doc_writer.
"""

import json
import logging
import re
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

# ── Keywords para detectar operacion ──────────────────────────────

WRITE_KEYWORDS = [
    "crea un documento", "crea un informe", "genera un documento", "genera un informe",
    "haz un documento", "haz un informe", "hazme un documento", "hazme un informe",
    "escribe un documento", "escribe un informe", "redacta un documento", "redacta un informe",
    "elabora un documento", "elabora un informe",
    "genera", "generar", "redacta", "redactar", "elabora", "elaborar",
    "escribe", "escribir", "crea un doc", "write", "create a document", "generate",
]

READ_KEYWORDS = [
    "lee el documento", "lee mi documento", "lee el archivo", "leer el documento",
    "abre el documento", "abre el archivo", "abrir el documento",
    "muestra el documento", "muestra el archivo", "mostrar el documento",
    "resume el documento", "resume el archivo", "resume el pdf", "resumeme el documento",
    "analiza el documento", "analiza el archivo", "analiza el pdf",
    "que dice el documento", "que contiene el documento", "contenido del documento",
    "puntos clave del documento", "puntos principales del documento",
    "lee", "leer", "abre", "abrir", "muestra", "mostrar",
    "resume", "resumir", "resumen", "resumeme",
    "analiza", "analizar", "analisis",
    "que dice", "que contiene", "contenido de",
    "puntos clave", "puntos principales",
    "read", "open", "show", "summarize", "analyze",
]

SUMMARY_KEYWORDS = {"resume", "resumir", "resumen", "resumeme", "resumir", "summarize", "summary"}
ANALYZE_KEYWORDS = {"analiza", "analizar", "analisis", "puntos clave", "puntos principales", "analyze", "analysis"}

PDF_FORMAT_KEYWORDS = {"en pdf", "formato pdf", "como pdf", "un pdf", "en formato pdf"}


def _normalize(text: str) -> str:
    """Minusculas y sin acentos."""
    text = (text or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _detect_operation(text: str) -> str:
    normalized = _normalize(text)
    for kw in WRITE_KEYWORDS:
        if _normalize(kw) in normalized:
            return "write"
    for kw in READ_KEYWORDS:
        if _normalize(kw) in normalized:
            return "read"
    return "read"


def _detect_read_mode(text: str) -> str:
    normalized = _normalize(text)
    for kw in ANALYZE_KEYWORDS:
        if _normalize(kw) in normalized:
            return "analyze"
    for kw in SUMMARY_KEYWORDS:
        if _normalize(kw) in normalized:
            return "summary"
    return "full"


def _detect_write_format(text: str) -> str:
    normalized = _normalize(text)
    for kw in PDF_FORMAT_KEYWORDS:
        if kw in normalized:
            return "pdf"
    return "txt"


def _extract_analyze_points(text: str) -> str:
    """Intenta extraer los puntos concretos que el usuario quiere analizar."""
    patterns = [
        r"analiza\s+(.+)",
        r"puntos\s+(?:clave|principales)\s+(?:de|del|sobre)\s+(.+)",
        r"analyze\s+(.+)",
    ]
    normalized = (text or "").strip()
    for pat in patterns:
        match = re.search(pat, normalized, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _resolve_project_from_message(text: str, context: dict):
    """Busca un proyecto mencionado en el mensaje. Devuelve (project_id, goal_id) o (None, None)."""
    normalized = _normalize(text)
    best_project = None
    for project in context.get("projects", []):
        title = _normalize(project.get("titulo") or "")
        if title and title in normalized:
            best_project = project
            break

    if not best_project:
        return None, None

    project_id = str(best_project.get("_id", ""))

    best_goal = None
    for goal in context.get("goals", []):
        goal_proj = str(goal.get("project_id", ""))
        if goal_proj == project_id:
            goal_title = _normalize(goal.get("titulo") or "")
            if goal_title and goal_title in normalized:
                best_goal = goal
                break

    goal_id = str(best_goal["_id"]) if best_goal else None
    return project_id, goal_id


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
    """Nodo organizador: clasifica read/write y prepara contexto (sin LLM)."""
    messages = state.get("messages", [])
    user_text = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and getattr(msg, "type", None) == "human":
            user_text = (msg.content or "").strip()
            break

    context = {}
    try:
        context = json.loads(state.get("context_json") or "{}")
    except Exception:
        pass

    user_id = state.get("user_id", "")

    # Si el supervisor ya resolvió doc_op, usarlo; si no, detectar por keywords
    doc_op = state.get("doc_op") or _detect_operation(user_text)

    # ── NOTE READ ─────────────────────────────────────────────────
    if doc_op == "read_notes":
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
        write_format = _detect_write_format(user_text)
        project_id, goal_id = _resolve_project_from_message(user_text, context)
        return {
            "doc_op": "write",
            "doc_write_format": write_format,
            "doc_target_project_id": project_id or "",
            "doc_target_goal_id": goal_id or "",
        }

    # ── FILE READ ─────────────────────────────────────────────────
    read_mode = _detect_read_mode(user_text)
    analyze_points = _extract_analyze_points(user_text) if read_mode == "analyze" else ""

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

    # Si el supervisor ya resolvió el documento, usarlo directamente
    preresolved_id = state.get("doc_target_id", "")
    if preresolved_id:
        doc = ProjectDocumentModel.get_document_by_id(preresolved_id, usuario_id=user_id)
        if not doc:
            msg = f"No se encontró el documento con ID '{preresolved_id}'."
            return {"doc_error": msg, "final_response": msg}
        project_id = str(doc.get("project_id", ""))
        goal_id = str(doc.get("goal_id", "")) if doc.get("goal_id") else ""
    else:
        project_id, goal_id = _resolve_project_from_message(user_text, context)
        doc, error = _find_document(user_text, user_id, project_id)
        if error:
            return {"doc_error": error, "final_response": error}

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
        "doc_target_project_id": project_id or str(doc.get("project_id", "")),
        "doc_target_goal_id": goal_id or str(doc.get("goal_id", "")),
        "doc_content_text": text_content,
        "doc_analyze_points": analyze_points,
    }
