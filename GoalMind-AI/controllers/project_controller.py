# controllers/project_controller.py
from io import BytesIO
import mimetypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, jsonify, make_response, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename
from bson import ObjectId

from model.goal_model import GoalModel
from model.project_document_folder_model import ProjectDocumentFolderModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from model.category_model import CategoryModel
from database.gridfs_storage import (
    delete_file_from_local_storage,
    delete_file_from_remote_storage,
    download_file_from_local_storage,
    download_file_from_remote_storage,
    promote_local_file_to_remote,
    upload_stream_to_local_storage,
)
from database.mongo_conn import queue_deletion, flush_deletion_queue, get_app_user_id

project_bp = Blueprint("project_bp", __name__, url_prefix="/projects")
DEFAULT_USER_ID = get_app_user_id()
TEXT_DOCUMENT_ENCODING = "utf-8"


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
    categories = CategoryModel.get_all_categories(usuario_id=DEFAULT_USER_ID)
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
    if doc_view.get("folder_id"):
        doc_view["folder_id"] = _serialize_id(doc_view["folder_id"])
    if doc_view.get("upload_id"):
        doc_view["upload_id"] = _serialize_id(doc_view["upload_id"])
    return doc_view


def _serialize_folder(folder):
    folder_view = dict(folder)
    if "_id" in folder_view:
        folder_view["_id"] = _serialize_id(folder_view["_id"])
    if folder_view.get("project_id"):
        folder_view["project_id"] = _serialize_id(folder_view["project_id"])
    return folder_view


def _same_id(left, right):
    return str(left) == str(right)


def _parse_importance(value, default=None):
    if value is None or value == "":
        return default
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return default


def _importance_value(project):
    return _parse_importance(project.get("importancia"), default=0) or 0


def _format_size(size):
    try:
        value = int(size or 0)
    except Exception:
        value = 0
    if value < 1024:
        return f"{value} B"
    if value < 1024**2:
        return f"{value / 1024:.1f} KB"
    if value < 1024**3:
        return f"{value / 1024**2:.1f} MB"
    return f"{value / 1024**3:.1f} GB"


def _document_name(doc):
    return (doc.get("original_name") or doc.get("filename") or "documento").strip()


def _resolve_document_mimetype(doc):
    content_type = (doc.get("content_type") or "").strip()
    name = _document_name(doc)
    if content_type and content_type != "application/octet-stream":
        return content_type
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _detect_preview_mode(doc, mimetype):
    name = _document_name(doc).lower()
    mt = (mimetype or "").lower()
    if mt == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if mt.startswith("image/"):
        return "image"
    if mt.startswith("text/") or name.endswith((".txt", ".md", ".csv", ".json", ".log")):
        return "text"
    return "unsupported"


def _decode_text_bytes(data):
    if data is None:
        return "", TEXT_DOCUMENT_ENCODING

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode(TEXT_DOCUMENT_ENCODING, errors="replace"), TEXT_DOCUMENT_ENCODING


def _document_project_url(doc):
    project_id = doc.get("project_id")
    if doc.get("folder_id"):
        return url_for("project_bp.view_project", project_id=project_id, folder=doc.get("folder_id"))
    return url_for("project_bp.view_project", project_id=project_id)


def _document_storage_metadata(doc):
    return {
        "project_id": str(doc.get("project_id", "")),
        "goal_id": str(doc.get("goal_id", "")) if doc.get("goal_id") else "",
        "folder_id": str(doc.get("folder_id", "")) if doc.get("folder_id") else "",
        "usuario_id": str(doc.get("usuario_id") or DEFAULT_USER_ID),
    }


def _document_view_payload(doc):
    doc_view = _serialize_document(doc)
    mimetype = _resolve_document_mimetype(doc_view)
    preview_mode = _detect_preview_mode(doc_view, mimetype)
    doc_id = doc_view.get("_id")
    doc_view["mimetype"] = mimetype
    doc_view["preview_mode"] = preview_mode
    doc_view["size_label"] = _format_size(doc_view.get("size"))
    doc_view["raw_url"] = url_for("project_bp.view_document", doc_id=doc_id)
    doc_view["open_url"] = url_for("project_bp.open_document", doc_id=doc_id)
    doc_view["download_url"] = url_for("project_bp.download_document", doc_id=doc_id)
    doc_view["text_url"] = url_for("project_bp.get_text_document_content", doc_id=doc_id)
    doc_view["text_update_url"] = url_for("project_bp.update_text_document", doc_id=doc_id)
    return doc_view


def _download_document_bytes(doc):
    local_id = doc.get("local_upload_id")
    if local_id:
        data = download_file_from_local_storage(local_id)
        if data is not None:
            return data
    remote_id = doc.get("upload_id")
    if remote_id:
        return download_file_from_remote_storage(remote_id, app=current_app)
    return None


def _stream_size(stream):
    try:
        current = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current)
        return size
    except Exception:
        return 0


def _created_at_value(project):
    return project.get("created_at") or datetime.min


# -------------------------------------------------------------
# LISTAR TODOS LOS PROYECTOS
# -------------------------------------------------------------
@project_bp.route("/", methods=["GET"])
def list_projects():
    try:
        projects = ProjectModel.get_all_projects(usuario_id=DEFAULT_USER_ID)
        goals = GoalModel.get_all_goals(usuario_id=DEFAULT_USER_ID)
        documents = ProjectDocumentModel.get_all_documents(usuario_id=DEFAULT_USER_ID)
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
        projects = [p for p in projects if (p.get("estado") or "Activo").strip().lower() == status_filter.lower()]

    priority_filter = (request.args.get("priority") or "").strip()
    if priority_filter and priority_filter.lower() != "all":
        projects = [p for p in projects if (p.get("prioridad") or "Media").strip().lower() == priority_filter.lower()]

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

        user_id = request.form.get("usuario_id") or DEFAULT_USER_ID
        data = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "categorias": categorias,
            "estado": request.form.get("estado") or "Activo",
            "prioridad": request.form.get("prioridad") or "Media",
            "importancia": _parse_importance(request.form.get("importancia"), default=5),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "usuario_id": user_id,
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
    project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
    if not project:
        flash("Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    goals = GoalModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    docs = ProjectDocumentModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    folders = ProjectDocumentFolderModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    categories = _load_categories()

    goals_view = [_serialize_goal(g) for g in goals]
    docs_view = [_document_view_payload(d) for d in docs]
    folders_view = [_serialize_folder(f) for f in folders]
    folder_map = {f["_id"]: f for f in folders_view if f.get("_id")}
    selected_folder_id = (request.args.get("folder") or "").strip()
    current_folder = folder_map.get(selected_folder_id) if selected_folder_id else None

    if selected_folder_id and not current_folder:
        flash("Carpeta no encontrada.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    folder_doc_counts = {folder_id: 0 for folder_id in folder_map}
    root_document_count = 0
    for doc in docs_view:
        folder_id = doc.get("folder_id")
        if folder_id and folder_id in folder_doc_counts:
            folder_doc_counts[folder_id] += 1
        else:
            root_document_count += 1

    if current_folder:
        current_documents = [d for d in docs_view if d.get("folder_id") == current_folder["_id"]]
    else:
        current_documents = [
            d for d in docs_view
            if not d.get("folder_id") or d.get("folder_id") not in folder_doc_counts
        ]

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
        tasks = TaskModel.get_tasks_by_goal(goal_id, usuario_id=DEFAULT_USER_ID)
        goal_tasks[goal_id] = [
            {
                "_id": _serialize_id(t.get("_id")),
                "titulo": t.get("contenido", "(Sin título)"),
                "estado": t.get("estado", "(Estado desconocido)"),
                "prioridad": t.get("prioridad", "(Prioridad desconocida)"),
            }
            for t in tasks
        ]

    category_names = _build_category_names(categories)

    return render_template(
        "partials/projects_templates/project_detail.html",
        project=_serialize_project(project),
        goals=goals_view,
        documents=current_documents,
        all_documents=docs_view,
        document_folders=folders_view,
        folder_doc_counts=folder_doc_counts,
        root_document_count=root_document_count,
        current_folder=current_folder,
        current_folder_id=current_folder["_id"] if current_folder else "",
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

        project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
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
        ProjectModel.update_project(project_id, {"notas": notes}, usuario_id=DEFAULT_USER_ID)
        flash("Anotacion agregada.", "success")
    except Exception as e:
        flash(f"Error al agregar anotacion: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


@project_bp.route("/<project_id>/notes/<note_id>/delete", methods=["POST"])
def delete_project_note(project_id, note_id):
    try:
        project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
        if not project:
            flash("Proyecto no encontrado.", "warning")
            return redirect(url_for("project_bp.list_projects"))

        notes = project.get("notas", []) or []
        notes = [n for n in notes if str(n.get("_id")) != str(note_id)]
        ProjectModel.update_project(project_id, {"notas": notes}, usuario_id=DEFAULT_USER_ID)
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
        }
        importance_value = _parse_importance(request.form.get("importancia"))
        if importance_value is not None:
            updates["importancia"] = importance_value
        
        # Solo actualizar categorias si se enviaron
        if categorias_raw:
            updates["categorias"] = categorias
            
        updates = {k: v for k, v in updates.items() if v not in [None, ""]}

        ProjectModel.update_project(project_id, updates, usuario_id=DEFAULT_USER_ID)
        flash("Proyecto actualizado correctamente", "success")
    except Exception as e:
        flash(f"Error al actualizar el proyecto: {e}", "danger")

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# ELIMINAR PROYECTO
# -------------------------------------------------------------
@project_bp.route("/delete/<project_id>", methods=["POST"])
def delete_project(project_id):
    errors = []

    # 1) Recolectar objetivos y tareas
    goals = []
    goal_ids = []
    task_ids = []
    try:
        goals = GoalModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
        goal_ids = [g.get("_id") for g in goals if g.get("_id")]
    except Exception as e:
        errors.append(f"objetivos: {e}")

    if goal_ids:
        for gid in goal_ids:
            try:
                tasks = TaskModel.get_tasks_by_goal(gid, usuario_id=DEFAULT_USER_ID)
                task_ids.extend([t.get("_id") for t in tasks if t.get("_id")])
            except Exception as e:
                errors.append(f"tareas: {e}")

    # 2) Eliminar tareas vinculadas
    if task_ids:
        try:
            TaskModel.delete_tasks_by_ids(task_ids, usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            errors.append(f"borrado tareas: {e}")
        for tid in task_ids:
            queue_deletion("Tasks", tid)

    # 3) Eliminar objetivos
    if goal_ids:
        try:
            GoalModel.delete_goals_by_ids(goal_ids, usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            errors.append(f"borrado objetivos: {e}")
        for gid in goal_ids:
            queue_deletion("Goals", gid)

    # 4) Eliminar documentos del proyecto
    try:
        docs = ProjectDocumentModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    except Exception as e:
        docs = []
        errors.append(f"documentos: {e}")

    for doc in docs:
        try:
            if not doc.get("upload_id"):
                local_path = doc.get("local_path")
                if local_path:
                    try:
                        Path(local_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            ProjectDocumentModel.delete_document(doc["_id"], usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            errors.append(f"borrado documento: {e}")
        queue_deletion("ProjectDocuments", doc.get("_id"))

    # 5) Eliminar el proyecto en sí
    try:
        folders = ProjectDocumentFolderModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    except Exception as e:
        folders = []
        errors.append(f"carpetas: {e}")

    for folder in folders:
        try:
            ProjectDocumentFolderModel.delete_folder(folder["_id"], usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            errors.append(f"borrado carpeta: {e}")
        queue_deletion("ProjectDocumentFolders", folder.get("_id"))

    try:
        ProjectModel.delete_project(project_id, usuario_id=DEFAULT_USER_ID)
    except Exception as e:
        errors.append(f"borrado proyecto: {e}")
    queue_deletion("Projects", project_id)

    # Intentar borrar en remoto inmediatamente si hay conexión
    try:
        flush_deletion_queue()
    except Exception as e:
        errors.append(f"sync remoto: {e}")

    if errors:
        flash("🗑️ Proyecto eliminado con advertencias. Revisa logs para detalles.", "warning")
    else:
        flash("🗑️ Proyecto eliminado correctamente", "success")

    return redirect(url_for("project_bp.list_projects"))


# -------------------------------------------------------------
# CARPETAS DE DOCUMENTOS
# -------------------------------------------------------------
@project_bp.route("/<project_id>/folders/add", methods=["POST"])
def add_document_folder(project_id):
    project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
    if not project:
        flash("Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    folder_name = (request.form.get("folder_name") or "").strip()
    if not folder_name:
        flash("La carpeta necesita un nombre.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    folders = ProjectDocumentFolderModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    for folder in folders:
        if (folder.get("name") or "").strip().lower() == folder_name.lower():
            flash("Ya existe una carpeta con ese nombre.", "warning")
            return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder["_id"]))

    folder = ProjectDocumentFolderModel.insert_folder(
        {"project_id": project_id, "name": folder_name},
        usuario_id=DEFAULT_USER_ID,
    )
    flash("Carpeta creada.", "success")
    return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder["_id"]))


@project_bp.route("/<project_id>/folders/<folder_id>/delete", methods=["POST"])
def delete_document_folder(project_id, folder_id):
    project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
    if not project:
        flash("Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    folder = ProjectDocumentFolderModel.get_folder_by_id(folder_id, usuario_id=DEFAULT_USER_ID)
    if not folder or not _same_id(folder.get("project_id"), project_id):
        flash("Carpeta no encontrada.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    docs = ProjectDocumentModel.get_by_project(project_id, usuario_id=DEFAULT_USER_ID)
    has_documents = any(
        _same_id(doc.get("folder_id"), folder_id)
        for doc in docs
        if doc.get("folder_id")
    )
    if has_documents:
        flash("Vacia la carpeta antes de eliminarla.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder_id))

    try:
        ProjectDocumentFolderModel.delete_folder(folder_id, usuario_id=DEFAULT_USER_ID)
        queue_deletion("ProjectDocumentFolders", folder_id)
        try:
            flush_deletion_queue()
        except Exception:
            pass
        flash("Carpeta eliminada.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar la carpeta: {e}", "danger")
        return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder_id))

    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# SUBIR DOCUMENTO A PROYECTO
# -------------------------------------------------------------
@project_bp.route("/<project_id>/documents", methods=["POST"])
def upload_document(project_id):
    project = ProjectModel.get_project_by_id(project_id, usuario_id=DEFAULT_USER_ID)
    if not project:
        flash("Proyecto no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    file = request.files.get("document")
    if not file or not file.filename:
        flash("Selecciona un archivo para subir.", "warning")
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    goal_id = request.form.get("goal_id") or None
    folder_id = request.form.get("folder_id") or None
    if folder_id:
        folder = ProjectDocumentFolderModel.get_folder_by_id(folder_id, usuario_id=DEFAULT_USER_ID)
        if not folder or not _same_id(folder.get("project_id"), project_id):
            flash("La carpeta seleccionada no existe.", "warning")
            folder_id = None

    safe_name = secure_filename(file.filename)
    if not safe_name:
        flash("Nombre de archivo no valido.", "warning")
        if folder_id:
            return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder_id))
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    content_type = file.mimetype or "application/octet-stream"
    metadata = {
        "project_id": str(project_id),
        "goal_id": str(goal_id) if goal_id else "",
        "folder_id": str(folder_id) if folder_id else "",
        "usuario_id": DEFAULT_USER_ID,
    }
    size = _stream_size(file.stream)
    local_upload_id = upload_stream_to_local_storage(
        file.stream,
        original_name=file.filename,
        content_type=content_type,
        metadata=metadata,
    )
    if not local_upload_id:
        flash("No se pudo guardar el documento.", "danger")
        if folder_id:
            return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder_id))
        return redirect(url_for("project_bp.view_project", project_id=project_id))

    remote_upload_id = None
    try:
        remote_upload_id = promote_local_file_to_remote(
            local_upload_id,
            original_name=file.filename,
            content_type=content_type,
            metadata=metadata,
            app=current_app,
        )
    except Exception:
        remote_upload_id = None

    doc_data = {
        "project_id": project_id,
        "goal_id": goal_id,
        "filename": safe_name,
        "original_name": file.filename,
        "content_type": content_type,
        "size": size,
    }
    if folder_id:
        doc_data["folder_id"] = folder_id
    if remote_upload_id:
        doc_data["upload_id"] = remote_upload_id
        doc_data["local_upload_id"] = local_upload_id
        doc_data["remote_sync_pending"] = False
    else:
        doc_data["local_upload_id"] = local_upload_id
        doc_data["remote_sync_pending"] = True

    ProjectDocumentModel.insert_document(doc_data, usuario_id=DEFAULT_USER_ID)
    flash("Documento subido correctamente", "success")

    if folder_id:
        return redirect(url_for("project_bp.view_project", project_id=project_id, folder=folder_id))
    return redirect(url_for("project_bp.view_project", project_id=project_id))


# -------------------------------------------------------------
# DESCARGAR DOCUMENTO
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/download", methods=["GET"])
def download_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    data = _download_document_bytes(doc)
    if not data:
        flash("Archivo no encontrado en almacenamiento.", "warning")
        if doc.get("folder_id"):
            return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id"), folder=doc.get("folder_id")))
        return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))

    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name=_document_name(doc),
        mimetype=_resolve_document_mimetype(doc),
    )


# -------------------------------------------------------------
# VER DOCUMENTO (INLINE)
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/view", methods=["GET"])
def view_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    data = _download_document_bytes(doc)
    if not data:
        flash("Archivo no encontrado en almacenamiento.", "warning")
        if doc.get("folder_id"):
            return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id"), folder=doc.get("folder_id")))
        return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))

    return send_file(
        BytesIO(data),
        as_attachment=False,
        download_name=_document_name(doc),
        mimetype=_resolve_document_mimetype(doc),
    )


# -------------------------------------------------------------
# ABRIR DOCUMENTO EN VISOR
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/open", methods=["GET"])
def open_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    mimetype = _resolve_document_mimetype(doc)
    preview_mode = _detect_preview_mode(doc, mimetype)
    data = None
    text_content = ""
    text_encoding = TEXT_DOCUMENT_ENCODING

    if preview_mode == "text":
        data = _download_document_bytes(doc)
        if data is None:
            flash("Archivo no encontrado en almacenamiento.", "warning")
            return redirect(_document_project_url(doc))
        text_content, text_encoding = _decode_text_bytes(data)

    return render_template(
        "partials/projects_templates/project_document_viewer.html",
        doc=_serialize_document(doc),
        document_name=_document_name(doc),
        document_size=_format_size(doc.get("size")),
        mimetype=mimetype,
        preview_mode=preview_mode,
        text_content=text_content,
        text_encoding=text_encoding,
        raw_url=url_for("project_bp.view_document", doc_id=doc_id),
        download_url=url_for("project_bp.download_document", doc_id=doc_id),
        back_url=_document_project_url(doc),
        page="projects",
    )


@project_bp.route("/documents/<doc_id>/text", methods=["GET"])
def get_text_document_content(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        return jsonify({"error": "Documento no encontrado."}), 404

    mimetype = _resolve_document_mimetype(doc)
    if _detect_preview_mode(doc, mimetype) != "text":
        return jsonify({"error": "Este formato no se puede editar."}), 400

    data = _download_document_bytes(doc)
    if data is None:
        return jsonify({"error": "Archivo no encontrado en almacenamiento."}), 404

    text_content, text_encoding = _decode_text_bytes(data)
    return jsonify({
        "content": text_content,
        "encoding": text_encoding,
        "name": _document_name(doc),
        "mimetype": mimetype,
        "size": _format_size(doc.get("size")),
    })


@project_bp.route("/documents/<doc_id>/text/update", methods=["POST"])
def update_text_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    mimetype = _resolve_document_mimetype(doc)
    if _detect_preview_mode(doc, mimetype) != "text":
        flash("Este formato no se puede editar desde la aplicacion.", "warning")
        return redirect(url_for("project_bp.open_document", doc_id=doc_id))

    text_content = request.form.get("content") or ""
    encoded = text_content.encode(TEXT_DOCUMENT_ENCODING)
    original_name = _document_name(doc)
    content_type = mimetype if mimetype != "application/octet-stream" else "text/plain"
    old_local_id = doc.get("local_upload_id")
    old_remote_id = doc.get("upload_id")

    new_local_id = upload_stream_to_local_storage(
        BytesIO(encoded),
        original_name=original_name,
        content_type=content_type,
        metadata=_document_storage_metadata(doc),
    )
    if not new_local_id:
        flash("No se pudo guardar el archivo editado.", "danger")
        return redirect(url_for("project_bp.open_document", doc_id=doc_id))

    new_remote_id = None
    try:
        new_remote_id = promote_local_file_to_remote(
            new_local_id,
            original_name=original_name,
            content_type=content_type,
            metadata=_document_storage_metadata(doc),
            app=current_app,
        )
    except Exception:
        new_remote_id = None

    updates = {
        "local_upload_id": new_local_id,
        "content_type": content_type,
        "size": len(encoded),
        "remote_sync_pending": not bool(new_remote_id),
    }
    if new_remote_id:
        updates["upload_id"] = new_remote_id

    ProjectDocumentModel.update_document(doc_id, updates, usuario_id=DEFAULT_USER_ID, sync_remote=True)

    if old_local_id and not _same_id(old_local_id, new_local_id):
        try:
            delete_file_from_local_storage(old_local_id)
        except Exception:
            pass
    if new_remote_id and old_remote_id and not _same_id(old_remote_id, new_remote_id):
        try:
            delete_file_from_remote_storage(old_remote_id, app=current_app)
        except Exception:
            pass

    flash("Archivo guardado.", "success")
    return redirect(url_for("project_bp.open_document", doc_id=doc_id))


# -------------------------------------------------------------
# ELIMINAR DOCUMENTO
# -------------------------------------------------------------
@project_bp.route("/documents/<doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = ProjectDocumentModel.get_document_by_id(doc_id, usuario_id=DEFAULT_USER_ID)
    if not doc:
        flash("Documento no encontrado.", "warning")
        return redirect(url_for("project_bp.list_projects"))

    try:
        ProjectDocumentModel.delete_document(doc_id, usuario_id=DEFAULT_USER_ID)
        flash("Documento eliminado", "success")
    except Exception as e:
        flash(f"No se pudo eliminar el documento completamente: {e}", "warning")
    queue_deletion("ProjectDocuments", str(doc_id))

    if doc.get("folder_id"):
        return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id"), folder=doc.get("folder_id")))
    return redirect(url_for("project_bp.view_project", project_id=doc.get("project_id")))
