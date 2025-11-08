from flask import Blueprint, render_template, request, redirect, url_for, flash
from model.task_model import TaskModel
from bson import ObjectId

from model.goal_model import GoalModel

task_bp = Blueprint("task_bp", __name__, url_prefix="/tasks")


# -------------------------------------------------------------
# 📋 LISTAR TODAS LAS TAREAS
# -------------------------------------------------------------
@task_bp.route("/", methods=["GET"])
def list_tasks():
    tasks = TaskModel.get_all_tasks()
    # 🔽 Traer objetivos
    goals = GoalModel.get_all_goals()

    # (Opcional pero recomendado) serializar _id para que el <option value="..."> no sea ObjectId('..')
    goals_view = []
    for g in goals:
        g = dict(g)
        if "_id" in g:
            g["_id"] = str(g["_id"])
        goals_view.append(g)

    return render_template(
        "partials/task_templates/task_menu.html",  # o tu plantilla de tareas principal
        tasks=tasks,
        goals=goals_view,
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
        return render_template("partials/task_templates/task_menu.html", selected_task=task, tasks=None, page="detail")
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
        if not tasks:
            flash("Este usuario aún no tiene tareas.", "info")
        return render_template(
            "partials/task_templates/task_menu.html",
            tasks=tasks,
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
        data = {
            "usuario_id": request.form.get("usuario_id"),
            "contenido": request.form.get("contenido"),
            "descripcion": request.form.get("descripcion"),
            "fecha_limite": request.form.get("fecha_limite"),
            "estado": request.form.get("estado") or "pendiente",
            "categoria": request.form.get("categoria"),
            "prioridad": request.form.get("prioridad") or "media",
            "objetivo_id": None,
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
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks,
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
    tasks = [task] if task else []
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks,
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
