# controllers/project_controller.py
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename
from bson import ObjectId

from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from model.upload_model import Upload_model
from model.category_model import CategoryModel
from database.mongo_conn import queue_deletion, flush_deletion_queue

project_bp = Blueprint("project_bp", __name__, url_prefix="/projects")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "66ffbbbbbbbbbbbbbbbb0100")


def _serialize_id(value):
    return str(value) if value is not None else None


def _serialize_project(project):
    project_view = dict(project)
    if "_id" in project_view:
        project_view["_id"] = _serialize_id(project_view["_id"])
    # Serializar categorias (array de ObjectIds)
    if project_view.get("categorias"):
        project_view["categorias"] = [str(cid) for cid in project_view["categorias"]]
    return project_view


def _load_categories():
    """Carga todas las categorias y las serializa para los templates."""
    categories = CategoryModel.get_all_categories()
    return [{
        "_id": str(c["_id"]),
        "name": c.get("name", "")
    } for c in categories]


def _build_category_names(categories):
    """Construye un diccionario {id: nombre} para lookup rapido en templates."""
    return {cat["_id"]: cat["name"] for cat in categories}


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
    if doc_view.get("upload_id"):
        doc_view["upload_id"] = _serialize_id(doc_view["upload_id"])
    return doc_view


def _format_size(size_bytes):
    if size_bytes is None:
        return "0 B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _parse_importance(value, default=None):
    if value is None or value == "":
        return default
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return default


def _importance_value(project):
    return _parse_importance(project.get("importancia"), default=0) or 0


def _created_at_value(project):
    return project.get("created_at") or datetime.min


# -------------------------------------------------------------
# LISTAR TODOS LOS PROYECTOS
# -------------------------------------------------------------
@project_bp.route("/", methods=["GET"])
def list_projects():
    try:
        projects = ProjectModel.get_all_projects()
        goals = GoalModel.get_all_goals()
        documents = ProjectDocumentModel.get_all_documents()
        categories = _load_categories()
    except Exception as e:
        flash(f"No se pudieron cargar los proyectos: {e}", "danger")
        projects, goals, documents = [], [], []
        categories = []

    goal_counts = {}
    goal_progress_sums = {}  # Suma de progresos por proyecto
    for goal in goals:
        project_id = goal.get("project_id")
        if project_id:
            key = str(project_id)
            goal_counts[key] = goal_counts.get(key, 0) + 1
            goal_progress_sums[key] = goal_progress_sums.get(key, 0) + (goal.get("progreso", 0) or 0)

    # Calcular progreso promedio por proyecto
    project_progress = {}
    for key, count in goal_counts.items():
        if count > 0:
            project_progress[key] = round(goal_progress_sums.get(key, 0) / count)
        else:
            project_progress[key] = 0

    doc_counts = {}
    for doc in documents:
        project_id = doc.get("project_id")
        if project_id:
            key = str(project_id)
            doc_counts[key] = doc_counts.get(key, 0) + 1

    sort_mode = request.args.get("order") or request.cookies.get("projects_sort") or "importance-desc"
    if sort_mode not in {"importance-desc", "importance-asc"}:
        sort_mode = "importance-desc"

    search_term = (request.args.get("q") or "").strip()
    if search_term:
        lowered = search_term.lower()
        projects = [p for p in projects if lowered in (p.get("titulo") or "").lower()]

    status_filter = (request.args.get("status") or "").strip()
    if status_filter and status_filter.lower() != "all":
        projects = [p for p in projects if (p.get("estado") or "").strip().lower() == status_filter.lower()]

    priority_filter = (request.args.get("priority") or "").strip()
    if priority_filter and priority_filter.lower() != "all":
        projects = [p for p in projects if (p.get("prioridad") or "").strip().lower() == priority_filter.lower()]

    category_filter = (request.args.get("category") or "").strip()
    if category_filter and category_filter.lower() != "all":
        projects = [p for p in projects if category_filter in [str(cid) for cid in p.get("categorias", [])]]

    active_projects = []
    other_projects = []
    for project in projects:
        if (project.get("estado") or "").strip().lower() == "activo":
            active_projects.append(project)
        else:
            other_projects.append(project)

    reverse_importance = sort_mode == "importance-desc"
    active_projects = sorted(active_projects, key=_created_at_value, reverse=True)
    active_projects.sort(key=_importance_value, reverse=reverse_importance)
    other_projects = sorted(other_projects, key=_created_at_value, reverse=True)
    projects_view = [_serialize_project(p) for p in (active_projects + other_projects)]
    category_names = _build_category_names(categories)

    response = make_response(render_template(
        "partials/projects_templates/project_menu.html",
        projects=projects_view,
        goal_counts=goal_counts,
        doc_counts=doc_counts,
        project_progress=project_progress,
        categories=categories,
        category_names=category_names,
        page="projects",
        project_sort=sort_mode,
        project_query=search_term,
        project_status=status_filter or "all",
        project_priority=priority_filter or "all",
        project_category=category_filter or "all",
    ))
    response.set_cookie("projects_sort", sort_mode, max_age=60 * 60 * 24 * 365)
    return response


# -------------------------------------------------------------
#CREAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/add", methods=["POST"])
def add_project():
    try:
        # Procesar categorias (pueden venir como lista o string separado por comas)
        categorias_raw = request.form.getlist("categorias")
        if not categorias_raw:
            cat_str = request.form.get("categorias", "")
            if cat_str:
                categorias_raw = [c.strip() for c in cat_str.split(",") if c.strip()]
        
        # Convertir a ObjectIds
        categorias = []
        for cat_id in categorias_raw:
            try:
                categorias.append(ObjectId(cat_id))
            except Exception:
                pass

        user_id = request.form.get("id_usuario") or DEFAULT_USER_ID
        data = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "categorias": categorias,
            "estado": request.form.get("estado") or "Activo",
            "prioridad": request.form.get("prioridad") or "Media",
            "importancia": _parse_importance(request.form.get("importancia"), default=5),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "id_usuario": user_id,
        }

        if not data["titulo"]:
            flash("El proyecto necesita un titulo.", "warning")
            return redirect(url_for("project_bp.list_projects"))

        ProjectModel.insert_project(data)
        flash("Proyecto creado correctamente", "success")
    except Exception as e:
        flash(f"Error al crear el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.list_projects"))


# -------------------------------------------------------------
# DETALLE DE PROYECTO
# -------------------------------------------------------------
@project_bp.route("/<project_id>", methods=["GET"])
def view_project(project_id):
    project = ProjectModel.get_project_by_id(project_id)
    if not project:
        flash("Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    goals = GoalModel.get_by_project(project_id)
    docs = ProjectDocumentModel.get_by_project(project_id)
    uploads = Upload_model.get_all_uploads()
    categories = _load_categories()

    goals_view = [_serialize_goal(g) for g in goals]
    docs_view = [_serialize_document(d) for d in docs]
    upload_views = []
    linked_upload_ids = {d.get("upload_id") for d in docs_view if d.get("upload_id")}

    for upload in uploads:
        upload_id = _serialize_id(upload.get("_id"))
        if upload_id in linked_upload_ids:
            continue
        upload_views.append(
            {
                "_id": upload_id,
                "title": upload.get("title") or upload.get("original_name") or "(sin nombre)",
                "original_name": upload.get("original_name") or "",
                "size_label": _format_size(upload.get("size", 0) or 0),
            }
        )

    goal_titles = {g["_id"]: g.get("titulo", "(sin titulo)") for g in goals_view}
    goal_documents = {g["_id"]: [] for g in goals_view}
    for doc in docs_view:
        gid = doc.get("goal_id")
        if gid and gid in goal_documents:
            goal_documents[gid].append(
                {
                    "_id": doc.get("_id"),
                    "name": doc.get("original_name") or doc.get("filename"),
                }
            )

    # Cargar tareas por objetivo
    goal_tasks = {}
    for goal in goals_view:
        goal_id = goal["_id"]
        tasks = TaskModel.get_tasks_by_goal(goal_id)
        goal_tasks[goal_id] = [
            {
                "_id": _serialize_id(t.get("_id")),
                "titulo": t.get("titulo", "(sin titulo)"),
                "estado": t.get("estado", "Pendiente"),
                "prioridad": t.get("prioridad", "Media"),
            }
            for t in tasks
        ]

    category_names = _build_category_names(categories)

    return render_template(
        "partials/projects_templates/project_detail.html",
        project=_serialize_project(project),
        goals=goals_view,
        documents=docs_view,
        uploads=upload_views,
        goal_titles=goal_titles,
        goal_documents=goal_documents,
        goal_tasks=goal_tasks,
        categories=categories,
        category_names=category_names,
        page="projects",
    )


# -------------------------------------------------------------
# ACTUALIZAR PROYECTO
# -------------------------------------------------------------
# -------------------------------------------------------------
# ANOTACIONES DE PROYECTO
# -------------------------------------------------------------
@project_bp.route("/<project_id>/notes/add", methods=["POST"])
def add_project_note(project_id):
    try:
        text = (request.form.get("note_text") or "").strip()
        if not text:
            flash("La anotacion no puede estar vacia.", "warning")
            return redirect(url_for("project_bp.view_project", project_id=project_id))

        project = ProjectModel.get_project_by_id(project_id)
        if not project:
            flash("Proyecto no encontrado.", "warning")
            return redirect(url_for("project_bp.list_projects"))

        note = {
            "_id": uuid4().hex,
            "text": text,
            "created_at": datetime.utcnow(),
        }
        notes = project.get("notas", []) or []
        notes.append(note)
        ProjectModel.update_project(project_id, {"notas": notes})
        flash("Anotacion agregada.", "success")
    except Exception as e:
        flash(f"Error al agregar anotacion: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


@project_bp.route("/<project_id>/notes/<note_id>/delete", methods=["POST"])
def delete_project_note(project_id, note_id):
    try:
        project = ProjectModel.get_project_by_id(project_id)
        if not project:
            flash("Proyecto no encontrado.", "warning")
            return redirect(url_for("project_bp.list_projects"))

        notes = project.get("notas", []) or []
        notes = [n for n in notes if str(n.get("_id")) != str(note_id)]
        ProjectModel.update_project(project_id, {"notas": notes})
        flash("Anotacion eliminada.", "success")
    except Exception as e:
        flash(f"Error al eliminar anotacion: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


@project_bp.route("/update/<project_id>", methods=["POST"])
def update_project(project_id):
    try:
        # Procesar categorias
        categorias_raw = request.form.getlist("categorias")
        if not categorias_raw:
            cat_str = request.form.get("categorias", "")
            if cat_str:
                categorias_raw = [c.strip() for c in cat_str.split(",") if c.strip()]
        
        categorias = []
        for cat_id in categorias_raw:
            try:
                categorias.append(ObjectId(cat_id))
            except Exception:
                pass

        updates = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
            "prioridad": request.form.get("prioridad"),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "id_usuario": request.form.get("id_usuario") or "",
        }
        importance_value = _parse_importance(request.form.get("importancia"))
        if importance_value is not None:
            updates["importancia"] = importance_value
        
        # Solo actualizar categorias si se enviaron
        if categorias_raw:
            updates["categorias"] = categorias
            
        updates = {k: v for k, v in updates.items() if v not in [None, ""]}

        ProjectModel.update_project(project_id, updates)
        flash("Proyecto actualizado correctamente", "success")
    except Exception as e:
        flash(f"Error al actualizar el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# ASOCIAR DOCUMENTO EXISTENTE
# -------------------------------------------------------------
@project_bp.route("/<project_id>/documents/link", methods=["POST"])
def link_upload_document(project_id):
    project = ProjectModel.get_project_by_id(project_id)
    if not project:
        flash("ƒsÿ‹÷? Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    upload_id = request.form.get("upload_id")
    if not upload_id:
        flash("ƒsÿ‹÷? Selecciona un documento para asociar.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    upload_doc = Upload_model.get_upload_by_id(upload_id)
    if not upload_doc:
        flash("ƒsÿ‹÷? Documento no encontrado en la biblioteca.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    goal_id = request.form.get("goal_id") or None

    doc_data = {
        "project_id": project_id,
        "goal_id": goal_id,
        "upload_id": upload_id,
        "filename": upload_doc.get("filename"),
        "original_name": upload_doc.get("original_name"),
        "content_type": upload_doc.get("content_type"),
        "size": upload_doc.get("size"),
        "local_path": upload_doc.get("local_path"),
    }

    ProjectDocumentModel.insert_document(doc_data)
    flash("Documento asociado correctamente", "success")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# ELIMINAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/delete/<project_id>", methods=["POST"])
def delete_project(project_id):
    try:
        # 1) Eliminar tareas vinculadas a los objetivos del proyecto
        goals = GoalModel.get_by_project(project_id)
        goal_ids = [g.get("_id") for g in goals if g.get("_id")]

        task_ids = []
        for gid in goal_ids:
            tasks = TaskModel.get_tasks_by_goal(gid)
            task_ids.extend([t.get("_id") for t in tasks if t.get("_id")])

        if task_ids:
            TaskModel.delete_tasks_by_ids(task_ids)
            for tid in task_ids:
                queue_deletion("Tasks", tid)

        # 2) Eliminar objetivos del proyecto
        if goal_ids:
            GoalModel.delete_goals_by_ids(goal_ids)
            for gid in goal_ids:
                queue_deletion("Goals", gid)

        # 3) Eliminar documentos del proyecto (y ficheros locales si aplica)
        docs = ProjectDocumentModel.get_by_project(project_id)
        for doc in docs:
            if not doc.get("upload_id"):
                local_path = doc.get("local_path")
                if local_path:
                    try:
                        Path(local_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            ProjectDocumentModel.delete_document(doc["_id"])
            queue_deletion("ProjectDocuments", doc.get("_id"))

        # 4) Eliminar el proyecto en sí
        ProjectModel.delete_project(project_id)
        queue_deletion("Projects", project_id)
        # Intentar borrar en remoto inmediatamente si hay conexión
        flush_deletion_queue()
        flash("🗑️ Proyecto eliminado correctamente", "success")
    except Exception as e:
        flash(f"❌ No se pudo eliminar el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.list_projects"))


# -------------------------------------------------------------
# SUBIR DOCUMENTO A PROYECTO
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
# DESCARGAR DOCUMENTO
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
# ELIMINAR DOCUMENTO
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id)
    if not doc:
        flash("⚠️ Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    if not doc.get("upload_id"):
        local_path = doc.get("local_path")
        if local_path:
            try:
                Path(local_path).unlink(missing_ok=True)
            except Exception:
                pass

    ProjectDocumentModel.delete_document(doc_id)
    flash("🗑️ Documento eliminado", "success")

    return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))
