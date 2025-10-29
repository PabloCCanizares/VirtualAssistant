from flask import Blueprint, render_template, request, redirect, url_for, flash
from model.task_model import TaskModel
from bson import ObjectId

task_bp = Blueprint("task_bp", __name__, url_prefix="/tasks")


# -------------------------------------------------------------
# 📋 LISTAR TODAS LAS TAREAS
# -------------------------------------------------------------
@task_bp.route("/", methods=["GET"])
def list_tasks():
    """Muestra todas las tareas disponibles."""
    tasks = TaskModel.get_all_tasks()
    return render_template("task_menu.html", tasks=tasks, selected_task=None, page="list")


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
        return render_template("task_menu.html", selected_task=task, tasks=None, page="detail")
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
        tasks = TaskModel.get_task_by_user(user_id)
        if not tasks:
            flash("Este usuario aún no tiene tareas.", "info")

        return render_template(
            "task_menu.html",
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