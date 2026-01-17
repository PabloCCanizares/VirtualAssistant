from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from model.task_model import TaskModel
from bson import ObjectId
from datetime import datetime

from model.goal_model import GoalModel
from model.project_model import ProjectModel

task_bp = Blueprint("task_bp", __name__, url_prefix="/tasks")


def _serialize_task(task):
    task_view = dict(task)
    if "_id" in task_view:
        task_view["_id"] = str(task_view["_id"])
    if task_view.get("objetivo_id"):
        task_view["objetivo_id"] = str(task_view["objetivo_id"])
    return task_view


def _load_goal_context():
    goals = GoalModel.get_all_goals()
    projects = ProjectModel.get_all_projects()

    project_titles = {}
    for project in projects:
        if "_id" in project:
            project_titles[str(project["_id"])] = project.get("titulo", "(sin titulo)")

    goals_view = []
    goal_titles = {}
    goal_project_titles = {}

    for goal in goals:
        goal_view = dict(goal)
        if "_id" in goal_view:
            gid = str(goal_view["_id"])
            goal_view["_id"] = gid
            goal_titles[gid] = goal_view.get("titulo", "(sin titulo)")
        else:
            continue

        if goal_view.get("project_id"):
            pid = str(goal_view["project_id"])
            goal_view["project_id"] = pid
            if pid in project_titles:
                goal_project_titles[gid] = project_titles[pid]

        goals_view.append(goal_view)

    return goals_view, goal_titles, goal_project_titles


# -------------------------------------------------------------
# 📋 LISTAR TODAS LAS TAREAS
# -------------------------------------------------------------
@task_bp.route("/", methods=["GET"])
def list_tasks():
    tasks = TaskModel.get_all_tasks()
    goals_view, goal_titles, goal_project_titles = _load_goal_context()
    tasks_view = [_serialize_task(t) for t in tasks]

    return render_template(
        "partials/task_templates/task_menu.html",  # o tu plantilla de tareas principal
        tasks=tasks_view,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        selected_category=None,
        page="list"
    )

# -------------------------------------------------------------
# 🔍 OBTENER UNA TAREA POR ID
# -------------------------------------------------------------
@task_bp.route("/<task_id>", methods=["GET"])
def view_task(task_id):
    """Muestra una tarea concreta (por ID)."""
    try:
        task = TaskModel.get_task_by_id(task_id)
        if not task:
            flash("❌ Tarea no encontrada", "warning")
            return redirect(url_for("task_bp.list_tasks"))
        goals_view, goal_titles, goal_project_titles = _load_goal_context()
        return render_template(
            "partials/task_templates/task_menu.html",
            selected_task=_serialize_task(task),
            tasks=None,
            goals=goals_view,
            goal_titles=goal_titles,
            goal_project_titles=goal_project_titles,
            page="detail"
        )
    except Exception as e:
        flash(f"Error al obtener la tarea: {e}", "danger")
        return redirect(url_for("task_bp.list_tasks"))
    
# -------------------------------------------------------------
# 🔍 OBTENER UNA TAREA POR USUARIO
# -------------------------------------------------------------
@task_bp.route("/user/<user_id>", methods=["GET"])
def list_tasks_by_user(user_id):
    """Muestra todas las tareas creadas por un usuario específico."""
    try:
        if user_id == 0:
            user_id = "66ffbbbbbbbbbbbbbbbb0100"
        tasks = TaskModel.get_task_by_user(user_id)
        tasks_view = [_serialize_task(t) for t in tasks]
        goals_view, goal_titles, goal_project_titles = _load_goal_context()
        if not tasks:
            flash("Este usuario aún no tiene tareas.", "info")
        return render_template(
            "partials/task_templates/task_menu.html",
            tasks=tasks_view,
            goals=goals_view,
            goal_titles=goal_titles,
            goal_project_titles=goal_project_titles,
            page="tareas",
            user_id=user_id
        )

    except Exception as e:
        flash(f" Error al obtener las tareas del usuario: {e}", "danger")
        return redirect(url_for("task_bp.list_tasks"))
# -------------------------------------------------------------
# ➕ CREAR UNA NUEVA TAREA
# -------------------------------------------------------------
@task_bp.route("/add", methods=["POST"])
def add_task():
    """Inserta una nueva tarea en la base local (y sincroniza con la nube)."""
    try:
        goal_id = request.form.get("objetivo_id")
        if not goal_id:
            flash("⚠️ Debes seleccionar un objetivo para crear una tarea.", "warning")
            return redirect(url_for("task_bp.list_tasks"))

        data = {
            "usuario_id": request.form.get("usuario_id"),
            "contenido": request.form.get("contenido"),
            "descripcion": request.form.get("descripcion"),
            "fecha_limite": request.form.get("fecha_limite"),
            "estado": request.form.get("estado") or "pendiente",
            "categoria": request.form.get("categoria"),
            "prioridad": request.form.get("prioridad") or "media",
            "objetivo_id": ObjectId(goal_id),
            "alarma_id": None,
        }
        TaskModel.insert_task(data)
        flash("✅ Tarea creada y sincronizada correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al crear la tarea: {e}", "danger")

    return redirect(url_for("task_bp.list_tasks"))


# -------------------------------------------------------------
# ✏️ ACTUALIZAR UNA TAREA EXISTENTE
# -------------------------------------------------------------
@task_bp.route("/update/<task_id>", methods=["POST"])
def update_task(task_id):
    """Actualiza una tarea existente y la sincroniza."""
    try:
        updates = {
            "contenido": request.form.get("contenido"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
            "categoria": request.form.get("categoria"),
            "prioridad": request.form.get("prioridad"),
            "fecha_limite": request.form.get("fecha_limite"),
        }
        if request.form.get("objetivo_id"):
            updates["objetivo_id"] = ObjectId(request.form.get("objetivo_id"))
        # Limpieza de valores vacíos
        updates = {k: v for k, v in updates.items() if v not in [None, ""]}

        TaskModel.update_task(task_id, updates)
        flash("♻️ Tarea actualizada correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al actualizar la tarea: {e}", "danger")

    return redirect(url_for("task_bp.view_task", task_id=task_id))


# -------------------------------------------------------------
# 🗑️ ELIMINAR UNA TAREA
# -------------------------------------------------------------
@task_bp.route("/delete/<task_id>", methods=["POST"])
def delete_task(task_id):
    """Elimina una tarea local y remota."""
    try:
        TaskModel.delete_task(task_id)
        flash("🗑️ Tarea eliminada correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al eliminar la tarea: {e}", "danger")

    return redirect(url_for("task_bp.list_tasks"))

    # -------------------------------------------------------------
# 🧮 FILTRAR POR CATEGORÍA (07-11-2025)
# -------------------------------------------------------------
@task_bp.route("/filter", methods=["GET"])
def filter_by_category():
    """Filtra las tareas por una categoría dada (?categoria=...)."""
    category = request.args.get("categoria", "").strip()
    tasks = TaskModel.get_tasks_by_category(category)
    tasks_view = [_serialize_task(t) for t in tasks]
    goals_view, goal_titles, goal_project_titles = _load_goal_context()
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks_view,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        selected_task=None,
        page="filter",
        selected_category=category
    )

# -------------------------------------------------------------
# 🔎 BUSCAR POR ID 07-11-2025
# -------------------------------------------------------------
@task_bp.route("/search", methods=["GET"])
def search_by_id():
    """Busca y muestra una tarea por su ID (?id=...)."""
    task_id = request.args.get("id", "").strip()
    task = None
    if task_id:
        try:
            task = TaskModel.get_task_by_id(task_id)
            if task is None:
                flash("No se encontró ninguna tarea con ese ID.", "warning")
        except Exception:
            flash("El ID proporcionado no es válido.", "danger")
    tasks = [_serialize_task(task)] if task else []
    goals_view, goal_titles, goal_project_titles = _load_goal_context()
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        selected_task=None,
        page="search",
        searched_id=task_id
    )


# -------------------------------------------------------------
# 🗑️🗑️ ELIMINACIÓN MASIVA (POST)
# -------------------------------------------------------------
@task_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete_tasks():
    ids = request.form.getlist("selected_tasks")
    if not ids:
        flash("No has seleccionado ninguna tarea.", "warning")
        return redirect(url_for("task_bp.list_tasks"))

    try:
        deleted = TaskModel.delete_tasks_by_ids(ids)
        flash(f"Se eliminaron {deleted} tarea(s).", "success")
    except Exception:
        flash("No se pudieron eliminar las tareas seleccionadas.", "danger")

    return redirect(url_for("task_bp.list_tasks"))


# -------------------------------------------------------------
# 📅 API: TAREAS POR RANGO DE FECHAS (para mini calendario)
# -------------------------------------------------------------
@task_bp.route("/api/by-date-range", methods=["GET"])
def get_tasks_by_date_range():
    """
    Devuelve tareas agrupadas por fecha para el mini calendario.
    Params: start (YYYY-MM-DD), end (YYYY-MM-DD)
    Response: { "2026-01-15": [{"titulo": "...", ...}, ...], ... }
    """
    try:
        start_str = request.args.get("start", "")
        end_str = request.args.get("end", "")

        if not start_str or not end_str:
            return jsonify({}), 200

        # Obtener todas las tareas
        tasks = TaskModel.get_all_tasks()

        # Agrupar por fecha_limite
        tasks_by_date = {}
        for task in tasks:
            fecha = task.get("fecha_limite")
            if not fecha:
                continue

            # Normalizar fecha a string YYYY-MM-DD
            if isinstance(fecha, datetime):
                date_key = fecha.strftime("%Y-%m-%d")
            elif isinstance(fecha, str):
                date_key = fecha[:10]
            else:
                continue

            # Verificar que esta en el rango
            if start_str <= date_key <= end_str:
                if date_key not in tasks_by_date:
                    tasks_by_date[date_key] = []
                tasks_by_date[date_key].append({
                    "titulo": task.get("contenido") or task.get("titulo") or "(Sin titulo)",
                    "estado": task.get("estado", "pendiente"),
                    "prioridad": task.get("prioridad", "media")
                })

        return jsonify(tasks_by_date), 200

    except Exception as e:
        print(f"Error en get_tasks_by_date_range: {e}")
        return jsonify({}), 200
