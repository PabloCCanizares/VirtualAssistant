from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from model.upload_model import Upload_model

upload_bp = Blueprint("upload_bp", __name__, url_prefix="/upload")


def _allowed_file(filename):
    allowed = current_app.config.get("UPLOAD_ALLOWED_EXTENSIONS")
    if not allowed:
        return True
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed


def _format_size(size_bytes):
    if size_bytes is None:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _serialize_upload(doc):
    doc_view = dict(doc)
    if "_id" in doc_view:
        doc_view["_id"] = str(doc_view["_id"])
    if doc_view.get("uploaded_at"):
        try:
            doc_view["uploaded_at"] = doc_view["uploaded_at"].strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    if "size" in doc_view:
        doc_view["size_label"] = _format_size(doc_view.get("size") or 0)
    return doc_view


@upload_bp.route("/", methods=["GET"])
def list_uploads():
    try:
        docs = Upload_model.get_all_uploads()
    except Exception as exc:
        flash(f"Error al cargar documentos: {exc}", "danger")
        docs = []

    docs_view = [_serialize_upload(d) for d in docs]
    total_size = _format_size(sum(d.get("size", 0) or 0 for d in docs))

    return render_template(
        "partials/upload_templates/upload_menu.html",
        documents=docs_view,
        total_size=total_size,
        page="uploads",
    )


@upload_bp.route("/submit", methods=["POST"])
def upload_file():
    file = request.files.get("document")
    if not file or not file.filename:
        flash("Selecciona un archivo para subir.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    if not _allowed_file(file.filename):
        flash("Tipo de archivo no permitido.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    safe_name = secure_filename(file.filename)
    if not safe_name:
        flash("Nombre de archivo no valido.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    upload_root = Path(current_app.config.get("UPLOAD_ROOT", "uploads"))
    docs_dir = upload_root / "user_uploads"
    docs_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}_{safe_name}"
    file_path = docs_dir / unique_name
    file.save(file_path)

    doc_data = {
        "title": request.form.get("title") or "",
        "filename": unique_name,
        "original_name": file.filename,
        "content_type": file.mimetype or "application/octet-stream",
        "size": file_path.stat().st_size,
        "local_path": str(file_path),
        "id_usuario": Upload_model.DEFAULT_USER_ID,
    }

    Upload_model.insert_upload(doc_data)
    flash("Documento subido correctamente", "success")

    return redirect(url_for("upload_bp.list_uploads"))


@upload_bp.route("/<doc_id>/download", methods=["GET"])
def download_upload(doc_id):
    doc = Upload_model.get_upload_by_id(doc_id)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    local_path = doc.get("local_path")
    if not local_path:
        flash("Documento sin ruta local.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    file_path = Path(local_path)
    if not file_path.exists():
        flash("Archivo no encontrado en disco.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    return send_file(file_path, as_attachment=True, download_name=doc.get("original_name") or file_path.name)


@upload_bp.route("/<doc_id>/view", methods=["GET"])
def view_upload(doc_id):
    doc = Upload_model.get_upload_by_id(doc_id)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    local_path = doc.get("local_path")
    if not local_path:
        flash("Documento sin ruta local.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    file_path = Path(local_path)
    if not file_path.exists():
        flash("Archivo no encontrado en disco.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    return send_file(file_path, as_attachment=False, download_name=doc.get("original_name") or file_path.name)


@upload_bp.route("/<doc_id>/delete", methods=["POST"])
def delete_upload(doc_id):
    doc = Upload_model.get_upload_by_id(doc_id)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("upload_bp.list_uploads"))

    local_path = doc.get("local_path")
    if local_path:
        try:
            Path(local_path).unlink(missing_ok=True)
        except Exception:
            pass

    Upload_model.delete_upload(doc_id)
    flash("Documento eliminado", "success")

    return redirect(url_for("upload_bp.list_uploads"))

