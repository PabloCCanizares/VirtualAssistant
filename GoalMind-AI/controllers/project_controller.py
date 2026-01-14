# controllers/project_controller.py
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel

project_bp = Blueprint("project_bp", __name__, url_prefix="/projects")


def _serialize_id(value):
    return str(value) if value is not None else None


def _serialize_project(project):
    project_view = dict(project)
    if "_id" in project_view:
        project_view["_id"] = _serialize_id(project_view["_id"])
    return project_view


def _serialize_goal(goal):
    goal_view = dict(goal)
    if "_id" in goal_view:
        goal_view["_id"] = _serialize_id(goal_view["_id"])
    if goal_view.get("project_id"):
        goal_view["project_id"] = _serialize_id(goal_view["project_id"])
    return goal_view


def _serialize_document(doc):
    doc_view = dict(doc)
    if "_id" in doc_view:
        doc_view["_id"] = _serialize_id(doc_view["_id"])
    if doc_view.get("project_id"):
        doc_view["project_id"] = _serialize_id(doc_view["project_id"])
    if doc_view.get("goal_id"):
        doc_view["goal_id"] = _serialize_id(doc_view["goal_id"])
    return doc_view


# -------------------------------------------------------------
# 📋 LISTAR TODOS LOS PROYECTOS
# -------------------------------------------------------------
@project_bp.route("/", methods=["GET"])
def list_projects():
    try:
        projects = ProjectModel.get_all_projects()
        goals = GoalModel.get_all_goals()
        documents = ProjectDocumentModel.get_all_documents()
    except Exception as e:
        flash(f"❌ No se pudieron cargar los proyectos: {e}", "danger")
        projects, goals, documents = [], [], []

    goal_counts = {}
    for goal in goals:
        project_id = goal.get("project_id")
        if project_id:
            key = str(project_id)
            goal_counts[key] = goal_counts.get(key, 0) + 1

    doc_counts = {}
    for doc in documents:
        project_id = doc.get("project_id")
        if project_id:
            key = str(project_id)
            doc_counts[key] = doc_counts.get(key, 0) + 1

    projects_view = [_serialize_project(p) for p in projects]

    return render_template(
        "partials/projects_templates/project_menu.html",
        projects=projects_view,
        goal_counts=goal_counts,
        doc_counts=doc_counts,
        page="projects",
    )


# -------------------------------------------------------------
# ➕ CREAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/add", methods=["POST"])
def add_project():
    try:
        data = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "categoria": request.form.get("categoria"),
            "estado": request.form.get("estado") or "Activo",
            "prioridad": request.form.get("prioridad") or "Media",
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "id_usuario": request.form.get("id_usuario") or "",
        }

        if not data["titulo"]:
            flash("⚠️ El proyecto necesita un título.", "warning")
            return redirect(url_for("project_bp.list_projects"))

        ProjectModel.insert_project(data)
        flash("✅ Proyecto creado correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al crear el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.list_projects"))


# -------------------------------------------------------------
# 🔎 DETALLE DE PROYECTO
# -------------------------------------------------------------
@project_bp.route("/<project_id>", methods=["GET"])
def view_project(project_id):
    project = ProjectModel.get_project_by_id(project_id)
    if not project:
        flash("⚠️ Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    goals = GoalModel.get_by_project(project_id)
    docs = ProjectDocumentModel.get_by_project(project_id)

    goals_view = [_serialize_goal(g) for g in goals]
    docs_view = [_serialize_document(d) for d in docs]

    goal_titles = {g["_id"]: g.get("titulo", "(sin titulo)") for g in goals_view}

    return render_template(
        "partials/projects_templates/project_detail.html",
        project=_serialize_project(project),
        goals=goals_view,
        documents=docs_view,
        goal_titles=goal_titles,
        page="projects",
    )


# -------------------------------------------------------------
# ✏️ ACTUALIZAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/update/<project_id>", methods=["POST"])
def update_project(project_id):
    try:
        updates = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "categoria": request.form.get("categoria"),
            "estado": request.form.get("estado"),
            "prioridad": request.form.get("prioridad"),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "id_usuario": request.form.get("id_usuario") or "",
        }
        updates = {k: v for k, v in updates.items() if v not in [None, ""]}

        ProjectModel.update_project(project_id, updates)
        flash("✅ Proyecto actualizado correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al actualizar el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# 🗑️ ELIMINAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/delete/<project_id>", methods=["POST"])
def delete_project(project_id):
    try:
        goals = GoalModel.get_by_project(project_id)
        if goals:
            flash("⚠️ Elimina primero los objetivos del proyecto.", "warning")
            return redirect(url_for("project_bp.view_project", project_id=project_id))

        docs = ProjectDocumentModel.get_by_project(project_id)
        for doc in docs:
            local_path = doc.get("local_path")
            if local_path:
                try:
                    Path(local_path).unlink(missing_ok=True)
                except Exception:
                    pass
            ProjectDocumentModel.delete_document(doc["_id"])

        ProjectModel.delete_project(project_id)
        flash("🗑️ Proyecto eliminado correctamente", "success")
    except Exception as e:
        flash(f"❌ No se pudo eliminar el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.list_projects"))


# -------------------------------------------------------------
# 📎 SUBIR DOCUMENTO A PROYECTO
# -------------------------------------------------------------
@project_bp.route("/<project_id>/documents", methods=["POST"])
def upload_document(project_id):
    project = ProjectModel.get_project_by_id(project_id)
    if not project:
        flash("⚠️ Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    file = request.files.get("document")
    if not file or not file.filename:
        flash("⚠️ Selecciona un archivo para subir.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    goal_id = request.form.get("goal_id") or None

    safe_name = secure_filename(file.filename)
    if not safe_name:
        flash("⚠️ Nombre de archivo no válido.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    upload_root = Path(current_app.config.get("UPLOAD_ROOT", "uploads"))
    project_dir = upload_root / "projects" / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}_{safe_name}"
    file_path = project_dir / unique_name
    file.save(file_path)

    doc_data = {
        "project_id": project_id,
        "goal_id": goal_id,
        "filename": unique_name,
        "original_name": file.filename,
        "content_type": file.mimetype or "application/octet-stream",
        "size": file_path.stat().st_size,
        "local_path": str(file_path),
    }

    ProjectDocumentModel.insert_document(doc_data)
    flash("📄 Documento subido correctamente", "success")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# ⬇️ DESCARGAR DOCUMENTO
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/download", methods=["GET"])
def download_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id)
    if not doc:
        flash("⚠️ Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    local_path = doc.get("local_path")
    if not local_path:
        flash("⚠️ Documento sin ruta local.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))

    file_path = Path(local_path)
    if not file_path.exists():
        flash("⚠️ Archivo no encontrado en disco.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))

    return send_file(file_path, as_attachment=True, download_name=doc.get("original_name") or file_path.name)


# -------------------------------------------------------------
# 🗑️ ELIMINAR DOCUMENTO
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id)
    if not doc:
        flash("⚠️ Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    local_path = doc.get("local_path")
    if local_path:
        try:
            Path(local_path).unlink(missing_ok=True)
        except Exception:
            pass

    ProjectDocumentModel.delete_document(doc_id)
    flash("🗑️ Documento eliminado", "success")

    return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))
