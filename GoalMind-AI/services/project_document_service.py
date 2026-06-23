from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from werkzeug.utils import secure_filename

from database.gridfs_storage import (
    download_file_from_local_storage,
    download_file_from_remote_storage,
    promote_local_file_to_remote,
    upload_stream_to_local_storage,
)
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from services.mongo_sync_service import flush_deletion_queue, queue_deletion


@dataclass
class DocumentCommandResult:
    ok: bool
    message: str
    level: str = "success"
    project_id: object | None = None
    redirect_to_list: bool = False
    document: dict | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class DocumentSourceResult:
    ok: bool
    message: str = ""
    level: str = "warning"
    document: dict | None = None
    file_bytes: bytes | None = None
    redirect_to_list: bool = False


def stream_size(stream) -> int:
    try:
        current_pos = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current_pos)
        return size
    except Exception:
        return 0


def document_name(doc: dict) -> str:
    return doc.get("original_name") or doc.get("filename") or "documento"


def resolve_document_mimetype(doc: dict) -> str:
    content_type = (doc.get("content_type") or "").strip()
    if content_type and content_type != "application/octet-stream":
        return content_type

    guessed_type, _ = mimetypes.guess_type(document_name(doc))
    return guessed_type or "application/octet-stream"


def detect_preview_mode(doc: dict, mimetype: str) -> str:
    filename = (doc.get("original_name") or doc.get("filename") or "").lower()
    if mimetype == "application/pdf" or filename.endswith(".pdf"):
        return "pdf"
    if mimetype.startswith("image/"):
        return "image"
    if mimetype.startswith("text/") or filename.endswith((".txt", ".md", ".csv", ".json", ".log")):
        return "text"
    return "unsupported"


def upload_project_document(
    project_id,
    file,
    *,
    goal_id=None,
    usuario_id,
    app=None,
    project_model=ProjectModel,
    document_model=ProjectDocumentModel,
    upload_local_fn=upload_stream_to_local_storage,
    promote_remote_fn=promote_local_file_to_remote,
    now_fn=datetime.utcnow,
    uuid_factory=uuid4,
) -> DocumentCommandResult:
    project = project_model.get_project_by_id(project_id, usuario_id=usuario_id)
    if not project:
        return DocumentCommandResult(
            ok=False,
            message="Proyecto no encontrado.",
            level="warning",
            redirect_to_list=True,
        )

    if not file or not file.filename:
        return DocumentCommandResult(
            ok=False,
            message="Selecciona un archivo para subir.",
            level="warning",
            project_id=project_id,
        )

    safe_name = secure_filename(file.filename)
    if not safe_name:
        return DocumentCommandResult(
            ok=False,
            message="Nombre de archivo no valido.",
            level="warning",
            project_id=project_id,
        )

    unique_name = f"{now_fn().strftime('%Y%m%d%H%M%S')}_{uuid_factory().hex}_{safe_name}"
    content_type = file.mimetype or "application/octet-stream"
    storage_metadata = {
        "project_id": str(project_id),
        "goal_id": str(goal_id) if goal_id else None,
        "usuario_id": usuario_id,
        "filename": unique_name,
    }
    local_upload_id = upload_local_fn(
        file.stream,
        original_name=file.filename,
        content_type=content_type,
        metadata=storage_metadata,
    )
    if local_upload_id is None:
        return DocumentCommandResult(
            ok=False,
            message="No se pudo guardar el documento en GridFS local.",
            level="danger",
            project_id=project_id,
        )

    doc_data = {
        "project_id": project_id,
        "goal_id": goal_id,
        "filename": unique_name,
        "original_name": file.filename,
        "content_type": content_type,
        "size": stream_size(file.stream),
        "local_upload_id": local_upload_id,
        "remote_sync_pending": True,
    }

    remote_upload_id = promote_remote_fn(
        local_upload_id,
        original_name=file.filename,
        content_type=content_type,
        metadata=storage_metadata,
        app=app,
    )
    if remote_upload_id is not None:
        doc_data["upload_id"] = remote_upload_id
        doc_data["remote_sync_pending"] = False
        document = document_model.insert_document(doc_data, usuario_id=usuario_id)
        return DocumentCommandResult(
            ok=True,
            message="Documento subido correctamente y sincronizado en remoto.",
            project_id=project_id,
            document=document,
        )

    document = document_model.insert_document(doc_data, usuario_id=usuario_id)
    return DocumentCommandResult(
        ok=True,
        message="Documento subido correctamente en local. Se sincronizara en remoto cuando haya conexion.",
        project_id=project_id,
        document=document,
    )


def resolve_document_source(
    doc: dict,
    *,
    app=None,
    download_local_fn=download_file_from_local_storage,
    download_remote_fn=download_file_from_remote_storage,
) -> DocumentSourceResult:
    local_upload_id = doc.get("local_upload_id")
    if local_upload_id:
        local_bytes = download_local_fn(local_upload_id)
        if local_bytes is not None:
            return DocumentSourceResult(ok=True, document=doc, file_bytes=local_bytes)

    upload_id = doc.get("upload_id")
    if upload_id:
        remote_bytes = download_remote_fn(upload_id, app)
        if remote_bytes is not None:
            return DocumentSourceResult(ok=True, document=doc, file_bytes=remote_bytes)

    return DocumentSourceResult(
        ok=False,
        document=doc,
        message="Archivo no encontrado ni en disco ni en remoto.",
    )


def get_project_document_source(
    doc_id,
    *,
    usuario_id,
    app=None,
    document_model=ProjectDocumentModel,
    download_local_fn=download_file_from_local_storage,
    download_remote_fn=download_file_from_remote_storage,
) -> DocumentSourceResult:
    doc = document_model.get_document_by_id(doc_id, usuario_id=usuario_id)
    if not doc:
        return DocumentSourceResult(
            ok=False,
            message="Documento no encontrado.",
            redirect_to_list=True,
        )

    return resolve_document_source(
        doc,
        app=app,
        download_local_fn=download_local_fn,
        download_remote_fn=download_remote_fn,
    )


def delete_project_document(
    doc_id,
    *,
    usuario_id,
    document_model=ProjectDocumentModel,
    queue_delete_fn=queue_deletion,
    flush_deletion_queue_fn=flush_deletion_queue,
) -> DocumentCommandResult:
    doc = document_model.get_document_by_id(doc_id, usuario_id=usuario_id)
    if not doc:
        return DocumentCommandResult(
            ok=False,
            message="Documento no encontrado.",
            level="warning",
            redirect_to_list=True,
        )

    errors = []

    try:
        document_model.delete_document(doc_id, usuario_id=usuario_id)
    except Exception as exc:
        errors.append(f"borrado local/remoto: {exc}")

    queue_delete_fn("ProjectDocuments", doc_id)

    try:
        flush_deletion_queue_fn()
    except Exception as exc:
        errors.append(f"sync remoto: {exc}")

    if errors:
        return DocumentCommandResult(
            ok=False,
            message=f"Documento eliminado localmente, con incidencias: {' | '.join(errors)}",
            level="warning",
            project_id=doc.get("project_id"),
            document=doc,
            errors=errors,
        )

    return DocumentCommandResult(
        ok=True,
        message="Documento eliminado",
        level="success",
        project_id=doc.get("project_id"),
        document=doc,
    )
