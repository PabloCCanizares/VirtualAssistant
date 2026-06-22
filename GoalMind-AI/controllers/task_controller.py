from datetime import datetime

from bson import ObjectId
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from database.mongo_conn import get_app_user_id
from model.category_model import CategoryModel
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel

task_bp = Blueprint("task_bp", __name__, url_prefix="/tasks")
DEFAULT_USER_ID = get_app_user_id()


def _serialize_task(task):
    task_view = dict(task)
    if "_id" in task_view:
        task_view["_id"] = str(task_view["_id"])
    if task_view.get("objetivo_id"):
        task_view["objetivo_id"] = str(task_view["objetivo_id"])
    # Serializar categorias (array de ObjectIds)
    if task_view.get("categorias"):
        task_view["categorias"] = [str(cid) for cid in task_view["categorias"]]
    # Serializar event_ids (array de ObjectIds de eventos asociados)
    if task_view.get("event_ids"):
        task_view["event_ids"] = [str(eid) for eid in task_view["event_ids"]]
    else:
        task_view["event_ids"] = []
    return task_view


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


def _get_category_names(category_ids):
    """
    Dado un array de category_ids, devuelve un dict {id: nombre}.
    """
    if not category_ids:
        return {}
    categories = CategoryModel.get_categories_by_ids(category_ids, usuario_id=DEFAULT_USER_ID)
    return {str(c["_id"]): c.get("name", "") for c in categories}


def _load_goal_context():
    goals = GoalModel.get_all_goals(usuario_id=DEFAULT_USER_ID)
    projects = ProjectModel.get_all_projects(usuario_id=DEFAULT_USER_ID)

    project_titles = {}
    project_dict = {}  # Para almacenar proyectos completos
    for project in projects:
        if "_id" in project:
            pid = str(project["_id"])
            project_titles[pid] = project.get("titulo", "(sin titulo)")
            project_dict[pid] = {
                "_id": pid,
                "titulo": project.get("titulo", "(sin titulo)"),
                "goals": []
            }

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
                # Añadir el objetivo al proyecto correspondiente
                if pid in project_dict:
                    project_dict[pid]["goals"].append({
                        "_id": gid,
                        "titulo": goal_view.get("titulo", "(sin titulo)")
                    })

        goals_view.append(goal_view)

    # Filtrar proyectos que tienen al menos un objetivo
    projects_with_goals = [p for p in project_dict.values() if len(p["goals"]) > 0]

    return goals_view, goal_titles, goal_project_titles, projects_with_goals


# -------------------------------------------------------------
# LISTAR TODAS LAS TAREAS
# -------------------------------------------------------------
@task_bp.route("/", methods=["GET"])
def list_tasks():
    tasks = TaskModel.get_all_tasks(usuario_id=DEFAULT_USER_ID)
    goals_view, goal_titles, goal_project_titles, projects_with_goals = _load_goal_context()
    tasks_view = [_serialize_task(t) for t in tasks]
    categories = _load_categories()
    category_names = _build_category_names(categories)

    return render_template(
        "partials/task_templates/task_menu.html",  # o tu plantilla de tareas principal
        tasks=tasks_view,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        projects_with_goals=projects_with_goals,
        categories=categories,
        category_names=category_names,
        selected_categories=[],
        selected_nombre="",
        page="list"
    )

# -------------------------------------------------------------
# OBTENER UNA TAREA POR ID
# -------------------------------------------------------------
@task_bp.route("/<task_id>", methods=["GET"])
def view_task(task_id):
    """Muestra una tarea concreta (por ID)."""
    try:
        task = TaskModel.get_task_by_id(task_id, usuario_id=DEFAULT_USER_ID)
        if not task:
            flash("Tarea no encontrada", "warning")
            return redirect(url_for("task_bp.list_tasks"))
        goals_view, goal_titles, goal_project_titles, projects_with_goals = _load_goal_context()
        categories = _load_categories()
        category_names = _build_category_names(categories)
        return render_template(
            "partials/task_templates/task_menu.html",
            selected_task=_serialize_task(task),
            tasks=None,
            goals=goals_view,
            goal_titles=goal_titles,
            goal_project_titles=goal_project_titles,
            projects_with_goals=projects_with_goals,
            categories=categories,
            category_names=category_names,
            page="detail"
        )
    except Exception as e:
        flash(f"Error al obtener la tarea: {e}", "danger")
        return redirect(url_for("task_bp.list_tasks"))
    
# -------------------------------------------------------------
# OBTENER UNA TAREA POR USUARIO
# -------------------------------------------------------------
@task_bp.route("/user", methods=["GET"])
@task_bp.route("/user/<user_id>", methods=["GET"])
def list_tasks_by_user(user_id=None):
    """Muestra todas las tareas creadas por un usuario espec??fico."""
    try:
        if user_id in (None, "0", 0):
            user_id = DEFAULT_USER_ID
        tasks = TaskModel.get_task_by_user(user_id)
        tasks_view = [_serialize_task(t) for t in tasks]
        goals_view, goal_titles, goal_project_titles, projects_with_goals = _load_goal_context()
        categories = _load_categories()
        category_names = _build_category_names(categories)
        if not tasks:
            flash("Este usuario aun no tiene tareas.", "info")
        return render_template(
            "partials/task_templates/task_menu.html",
            tasks=tasks_view,
            goals=goals_view,
            goal_titles=goal_titles,
            goal_project_titles=goal_project_titles,
            projects_with_goals=projects_with_goals,
            categories=categories,
            category_names=category_names,
            page="tareas",
            user_id=user_id
        )

    except Exception as e:
        flash(f"Error al obtener las tareas del usuario: {e}", "danger")
        return redirect(url_for("task_bp.list_tasks"))
# -------------------------------------------------------------
# CREAR UNA NUEVA TAREA
# -------------------------------------------------------------
@task_bp.route("/add", methods=["POST"])
def add_task():
    """Inserta una nueva tarea en la base local (y sincroniza con la nube)."""
    try:
        goal_id = request.form.get("objetivo_id")
        if not goal_id:
            flash("Debes seleccionar un objetivo para crear una tarea.", "warning")
            return redirect(url_for("task_bp.list_tasks"))

        # Procesar categorias: el selector envia un hidden input con IDs
        # separados por comas, por lo que hay que aplanar cada entrada.
        categorias_raw = []
        for item in request.form.getlist("categorias"):
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    categorias_raw.append(part)

        # Convertir a ObjectIds
        categorias = []
        for cat_id in categorias_raw:
            try:
                categorias.append(ObjectId(cat_id))
            except Exception:
                pass

        user_id = request.form.get("usuario_id") or DEFAULT_USER_ID
        data = {
            "usuario_id": user_id,
            "contenido": request.form.get("contenido"),
            "descripcion": request.form.get("descripcion"),
            "fecha_limite": request.form.get("fecha_limite"),
            "estado": request.form.get("estado") or "pendiente",
            "categorias": categorias,
            "prioridad": request.form.get("prioridad") or "media",
            "objetivo_id": ObjectId(goal_id),
            "alarma_id": None,
        }
        TaskModel.insert_task(data)
        flash("Tarea creada y sincronizada correctamente", "success")
    except Exception as e:
        flash(f"Error al crear la tarea: {e}", "danger")

    return redirect(url_for("task_bp.list_tasks"))


# -------------------------------------------------------------
# ACTUALIZAR UNA TAREA EXISTENTE
# -------------------------------------------------------------
@task_bp.route("/update/<task_id>", methods=["POST"])
def update_task(task_id):
    """Actualiza una tarea existente y la sincroniza."""
    try:
        # DEBUG: ver que manda realmente el form
        print(f"[update_task] form = {dict(request.form.lists())}")

        # Procesar categorias: aplanar CSV del hidden input del selector.
        categorias_raw = []
        for item in request.form.getlist("categorias"):
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    categorias_raw.append(part)
        print(f"[update_task] categorias_raw = {categorias_raw}")

        categorias = []
        for cat_id in categorias_raw:
            try:
                categorias.append(ObjectId(cat_id))
            except Exception:
                pass

        updates = {
            "contenido": request.form.get("contenido"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
            "prioridad": request.form.get("prioridad"),
            "fecha_limite": request.form.get("fecha_limite"),
        }
        
        # Solo actualizar categorias si se enviaron
        if categorias_raw:
            updates["categorias"] = categorias
            
        if request.form.get("objetivo_id"):
            updates["objetivo_id"] = ObjectId(request.form.get("objetivo_id"))
        
        # Limpieza de valores vacios (pero mantener arrays vacios si se enviaron)
        updates = {k: v for k, v in updates.items() if v not in [None, ""]}

        TaskModel.update_task(task_id, updates, usuario_id=DEFAULT_USER_ID)
        flash("Tarea actualizada correctamente", "success")
    except Exception as e:
        flash(f"Error al actualizar la tarea: {e}", "danger")

    return redirect(url_for("task_bp.view_task", task_id=task_id))


# -------------------------------------------------------------
#  ELIMINAR UNA TAREA
# -------------------------------------------------------------
@task_bp.route("/delete/<task_id>", methods=["POST"])
def delete_task(task_id):
    """Elimina una tarea local y remota."""
    try:
        TaskModel.delete_task(task_id, usuario_id=DEFAULT_USER_ID)
        flash(" Tarea eliminada correctamente", "success")
    except Exception as e:
        flash(f" Error al eliminar la tarea: {e}", "danger")

    return redirect(url_for("task_bp.list_tasks"))

    # -------------------------------------------------------------
# BUSCAR TAREAS POR NOMBRE Y/O CATEGORÍA
# -------------------------------------------------------------
@task_bp.route("/filter", methods=["GET"])
def filter_by_category():
    """
    Busca tareas por nombre y/o categoria.
    Parametros: ?nombre=...&categoria=... (categoria ahora es un ID o lista de IDs)
    Busca en todas las tareas sin importar el usuario dueno.
    """
    nombre = request.args.get("nombre", "").strip()
    # Acepta tanto ?categoria=id1&categoria=id2 como ?categoria=id1,id2,id3
    raw_cats = request.args.getlist("categoria")
    categoria_ids = []
    for item in raw_cats:
        for part in item.split(","):
            part = part.strip()
            if part:
                categoria_ids.append(part)

    tasks = TaskModel.search_tasks(nombre=nombre, category_ids=categoria_ids if categoria_ids else None, usuario_id=DEFAULT_USER_ID)
    tasks_view = [_serialize_task(t) for t in tasks]
    goals_view, goal_titles, goal_project_titles, projects_with_goals = _load_goal_context()
    categories = _load_categories()
    category_names = _build_category_names(categories)
    
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks_view,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        projects_with_goals=projects_with_goals,
        categories=categories,
        category_names=category_names,
        selected_task=None,
        page="filter",
        selected_categories=categoria_ids,
        selected_nombre=nombre,
    )

# -------------------------------------------------------------
#  BUSCAR POR ID 07-11-2025
# -------------------------------------------------------------
@task_bp.route("/search", methods=["GET"])
def search_by_id():
    """Busca y muestra una tarea por su ID (?id=...)."""
    task_id = request.args.get("id", "").strip()
    task = None
    if task_id:
        try:
            task = TaskModel.get_task_by_id(task_id, usuario_id=DEFAULT_USER_ID)
            if task is None:
                flash("No se encontro ninguna tarea con ese ID.", "warning")
        except Exception:
            flash("El ID proporcionado no es valido.", "danger")
    tasks = [_serialize_task(task)] if task else []
    goals_view, goal_titles, goal_project_titles, projects_with_goals = _load_goal_context()
    categories = _load_categories()
    category_names = _build_category_names(categories)
    return render_template(
        "partials/task_templates/task_menu.html",
        tasks=tasks,
        goals=goals_view,
        goal_titles=goal_titles,
        goal_project_titles=goal_project_titles,
        projects_with_goals=projects_with_goals,
        categories=categories,
        category_names=category_names,
        selected_task=None,
        page="search",
        searched_id=task_id
    )


# -------------------------------------------------------------
#  ELIMINACIÓN MASIVA (POST)
# -------------------------------------------------------------
@task_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete_tasks():
    # Soportar tanto form data como JSON
    if request.is_json:
        data = request.get_json()
        ids = data.get("selected_tasks", [])
    else:
        ids = request.form.getlist("selected_tasks")
    
    if not ids:
        if request.is_json:
            return jsonify({"success": False, "message": "No has seleccionado ninguna tarea."}), 400
        flash("No has seleccionado ninguna tarea.", "warning")
        return redirect(url_for("task_bp.list_tasks"))

    try:
        deleted = TaskModel.delete_tasks_by_ids(ids, usuario_id=DEFAULT_USER_ID)
        if request.is_json:
            return jsonify({"success": True, "message": f"Se eliminaron {deleted} tarea(s).", "deleted_count": deleted})
        flash(f"Se eliminaron {deleted} tarea(s).", "success")
    except Exception:
        if request.is_json:
            return jsonify({"success": False, "message": "No se pudieron eliminar las tareas seleccionadas."}), 500
        flash("No se pudieron eliminar las tareas seleccionadas.", "danger")

    return redirect(url_for("task_bp.list_tasks"))


# -------------------------------------------------------------
# ASIGNAR OBJETIVO A MÚLTIPLES TAREAS (POST)
# -------------------------------------------------------------
@task_bp.route("/bulk-assign-goal", methods=["POST"])
def bulk_assign_goal():
    """
    Asigna un objetivo a múltiples tareas seleccionadas.
    Espera JSON con: { "selected_tasks": [...], "objetivo_id": "..." }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No se recibieron datos."}), 400
        
        task_ids = data.get("selected_tasks", [])
        goal_id = data.get("objetivo_id")
        
        if not task_ids:
            return jsonify({"success": False, "message": "No has seleccionado ninguna tarea."}), 400
        
        if not goal_id:
            return jsonify({"success": False, "message": "No has seleccionado ningún objetivo."}), 400
        
        # Verificar que el objetivo existe
        goal = GoalModel.get_goal_by_id(goal_id, usuario_id=DEFAULT_USER_ID)
        if not goal:
            return jsonify({"success": False, "message": "El objetivo seleccionado no existe."}), 404
        
        # Asignar el objetivo a las tareas
        updated_count = TaskModel.assign_goal_to_tasks(task_ids, goal_id, usuario_id=DEFAULT_USER_ID)
        
        return jsonify({
            "success": True,
            "message": f"Se asignaron {updated_count} tarea(s) al objetivo '{goal.get('titulo', 'Sin título')}'.",
            "updated_count": updated_count
        })
        
    except Exception as e:
        print(f"Error en bulk_assign_goal: {e}")
        return jsonify({"success": False, "message": f"Error al asignar objetivo: {str(e)}"}), 500


# -------------------------------------------------------------
# API: TAREAS POR RANGO DE FECHAS (para mini calendario)
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
        tasks = TaskModel.get_all_tasks(usuario_id=DEFAULT_USER_ID)

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
