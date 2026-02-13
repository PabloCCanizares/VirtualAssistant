# controllers/goal_controller.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database.mongo_conn import queue_deletion, flush_deletion_queue, get_app_user_id
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from model.category_model import CategoryModel
from bson import ObjectId

goal_bp = Blueprint("goal_bp", __name__, url_prefix="/goals")
DEFAULT_USER_ID = get_app_user_id()


def _serialize_goal(goal):
    goal_view = dict(goal)
    if "_id" in goal_view:
        goal_view["_id"] = str(goal_view["_id"])
    if goal_view.get("project_id"):
        goal_view["project_id"] = str(goal_view["project_id"])
    # Serializar categorias (array de ObjectIds)
    if goal_view.get("categorias"):
        goal_view["categorias"] = [str(cid) for cid in goal_view["categorias"]]
    # Serializar event_ids (array de ObjectIds de eventos asociados)
    if goal_view.get("event_ids"):
        goal_view["event_ids"] = [str(eid) for eid in goal_view["event_ids"]]
    else:
        goal_view["event_ids"] = []
    return goal_view


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


def _load_projects():
    projects = ProjectModel.get_all_projects()
    projects_view = []
    project_titles = {}
    for project in projects:
        project_view = dict(project)
        if "_id" in project_view:
            pid = str(project_view["_id"])
            project_view["_id"] = pid
            project_titles[pid] = project_view.get("titulo", "(sin titulo)")
        projects_view.append(project_view)
    return projects_view, project_titles

# -------------------------------------------------------------
# 📋 LISTAR TODOS LOS OBJETIVOS
# -------------------------------------------------------------
@goal_bp.route("/", methods=["GET"])
def list_goals():
    """Muestra todos los objetivos."""
    try:
        goals = GoalModel.get_all_goals()
        goals_view = [_serialize_goal(g) for g in goals]
        projects, project_titles = _load_projects()
        categories = _load_categories()
        category_names = _build_category_names(categories)

    except Exception as e:
        flash(f"No se pudieron cargar los objetivos: {e}", "danger")
        goals_view = []
        projects, project_titles = [], {}
        categories = []
        category_names = {}
    return render_template(
        "partials/goals_templates/goal_menu.html",
        goals=goals_view,
        projects=projects,
        project_titles=project_titles,
        categories=categories,
        category_names=category_names,
        selected_category=None,
        page="objetivos",
    )

# -------------------------------------------------------------
# 🔎 FILTRAR POR CATEGORÍA
# -------------------------------------------------------------
@goal_bp.route("/filter", methods=["GET"])
def filter_by_category():
    categoria_ids = request.args.getlist("categoria")
    try:
        if categoria_ids:
            goals = GoalModel.search_by_categories(categoria_ids)
            flash(f"Filtro aplicado", "info")
        else:
            goals = GoalModel.get_all_goals()
        goals_view = [_serialize_goal(g) for g in goals]
        projects, project_titles = _load_projects()
        categories = _load_categories()
        category_names = _build_category_names(categories)

    except Exception as e:
        flash(f"Error al filtrar: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))

    return render_template(
        "partials/goals_templates/goal_menu.html",
        goals=goals_view,
        projects=projects,
        project_titles=project_titles,
        categories=categories,
        category_names=category_names,
        selected_categories=categoria_ids,
        page="objetivos",
    )

# -------------------------------------------------------------
# ➕ CREAR OBJETIVO (estilo add_task)
# -------------------------------------------------------------
@goal_bp.route("/add", methods=["POST"])
def add_goal():
    """Inserta un nuevo objetivo en la base local (y sincroniza con la nube)."""
    try:
        project_id = request.form.get("project_id")
        if not project_id:
            flash("Debes seleccionar un proyecto antes de crear un objetivo.", "warning")
            return redirect(url_for("goal_bp.list_goals"))

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
            "id_usuario": user_id,
            "project_id": project_id,
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "categorias": categorias,
            "progreso": int(request.form.get("progreso") or 0),
            "estado": request.form.get("estado") or "En progreso",
            "prioridad": request.form.get("prioridad") or "Media",
            "alarma_id": request.form.get("alarma_id") or "",
        }

        GoalModel.insert_goal(data)
        flash("Objetivo creado y sincronizado correctamente", "success")
    except Exception as e:
        flash(f"Error al crear el objetivo: {e}", "danger")

    return redirect(url_for("goal_bp.list_goals"))



# -------------------------------------------------------------
# 🔎 VER DETALLE DE UN OBJETIVO
# -------------------------------------------------------------
@goal_bp.route("/<goal_id>", methods=["GET"])
def view_goal(goal_id):
    """Muestra el detalle de un objetivo especifico."""
    try:
        goal = GoalModel.get_goal_by_id(goal_id)
        if not goal:
            flash("Objetivo no encontrado.", "warning")
            return redirect(url_for("goal_bp.list_goals"))

        goal_view = _serialize_goal(goal)
        projects, project_titles = _load_projects()
        categories = _load_categories()
        category_names = _build_category_names(categories)

        # Obtener tareas asociadas a este objetivo
        tasks = TaskModel.get_tasks_by_goal(goal_id)
        tasks_view = []
        for task in tasks:
            task_view = dict(task)
            if "_id" in task_view:
                task_view["_id"] = str(task_view["_id"])
            if task_view.get("objetivo_id"):
                task_view["objetivo_id"] = str(task_view["objetivo_id"])
            if task_view.get("categorias"):
                task_view["categorias"] = [str(cid) for cid in task_view["categorias"]]
            tasks_view.append(task_view)

        return render_template(
            "partials/goals_templates/goal_detail.html",
            goal=goal_view,
            projects=projects,
            project_titles=project_titles,
            categories=categories,
            category_names=category_names,
            tasks=tasks_view,
            page="objetivos",
        )
    except Exception as e:
        flash(f"Error al cargar el objetivo: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))


# -------------------------------------------------------------
# ✏️ ACTUALIZAR OBJETIVO (edición inline)
# -------------------------------------------------------------
@goal_bp.route("/<goal_id>", methods=["POST"])
def update_goal(goal_id):
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
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "estado": request.form.get("estado"),
            "prioridad": request.form.get("prioridad"),
            "alarma_id": request.form.get("alarma_id"),
        }
        
        # Solo actualizar categorias si se enviaron
        if categorias_raw:
            updates["categorias"] = categorias
            
        if request.form.get("progreso") is not None:
            try:
                updates["progreso"] = int(request.form.get("progreso") or 0)
            except ValueError:
                pass
        if request.form.get("id_usuario"):
            updates["id_usuario"] = request.form.get("id_usuario")
        if request.form.get("project_id"):
            updates["project_id"] = request.form.get("project_id")

        GoalModel.update_goal(goal_id, updates)
        flash("Objetivo actualizado correctamente", "success")
    except Exception as e:
        flash(f"Error al actualizar el objetivo: {e}", "danger")

    redirect_to = (request.form.get("redirect_to") or "").strip()
    if redirect_to.startswith("/"):
        return redirect(redirect_to)

    return redirect(url_for("goal_bp.list_goals"))

# -------------------------------------------------------------
# 🗑️ ELIMINAR OBJETIVO (individual)
# -------------------------------------------------------------
@goal_bp.route("/delete/<goal_id>", methods=["POST"])
def delete_goal(goal_id):
    try:
        task_ids = []
        try:
            tasks = TaskModel.get_tasks_by_goal(goal_id)
            task_ids = [t.get("_id") for t in tasks if t.get("_id")]
        except Exception:
            task_ids = []

        if task_ids:
            try:
                TaskModel.delete_tasks_by_ids(task_ids)
            except Exception:
                pass
            for tid in task_ids:
                queue_deletion("Tasks", tid)

        deleted = GoalModel.delete_goal(goal_id)
        if deleted:
            queue_deletion("Goals", goal_id)
            try:
                flush_deletion_queue()
            except Exception:
                pass
        if deleted:
            flash("🗑️ Objetivo eliminado correctamente", "success")
        else:
            flash("⚠️ No se encontró el objetivo a eliminar", "warning")
    except Exception as e:
        flash(f"❌ No se pudo eliminar el objetivo: {e}", "danger")
    redirect_to = (request.form.get("redirect_to") or "").strip()
    if redirect_to.startswith("/"):
        return redirect(redirect_to)
    return redirect(url_for("goal_bp.list_goals"))

# -------------------------------------------------------------
# 🗑️🗑️ ELIMINAR MÚLTIPLES OBJETIVOS
# -------------------------------------------------------------
@goal_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete_goals():
    ids = request.form.getlist("selected_goals")
    if not ids:
        flash("No has seleccionado ningún objetivo.", "warning")
        return redirect(url_for("goal_bp.list_goals"))

    try:
        task_ids = []
        for gid in ids:
            try:
                tasks = TaskModel.get_tasks_by_goal(gid)
                task_ids.extend([t.get("_id") for t in tasks if t.get("_id")])
            except Exception:
                continue
        if task_ids:
            try:
                TaskModel.delete_tasks_by_ids(task_ids)
            except Exception:
                pass
            for tid in task_ids:
                queue_deletion("Tasks", tid)

        deleted = GoalModel.delete_goals_by_ids(ids)
        for gid in ids:
            queue_deletion("Goals", gid)
        try:
            flush_deletion_queue()
        except Exception:
            pass
        flash(f"Se eliminaron {deleted} objetivo(s).", "success")
    except Exception as e:
        flash(f"❌ No se pudieron eliminar los objetivos seleccionados: {e}", "danger")

    return redirect(url_for("goal_bp.list_goals"))

# -------------------------------------------------------------
# API: Actualizar objetivo via JSON (para modal)
# -------------------------------------------------------------
@goal_bp.route("/api/<goal_id>", methods=["PUT", "PATCH"])
def api_update_goal(goal_id):
    """Actualiza un objetivo via JSON y devuelve el resultado."""
    from bson import ObjectId

    try:
        payload = request.get_json(silent=True) or {}

        updates = {}
        for field in ["titulo", "descripcion", "fecha_inicio", "fecha_fin",
                      "estado", "prioridad", "alarma_id", "id_usuario", "project_id"]:
            if field in payload:
                updates[field] = payload[field]

        # Manejar progreso
        if "progreso" in payload:
            try:
                updates["progreso"] = int(payload["progreso"] or 0)
            except ValueError:
                pass

        # Manejar categorias (array de IDs)
        if "categorias" in payload:
            categorias_raw = payload["categorias"]
            if isinstance(categorias_raw, list):
                categorias_oids = []
                for cat_id in categorias_raw:
                    if cat_id:
                        try:
                            categorias_oids.append(ObjectId(str(cat_id)))
                        except Exception:
                            pass
                updates["categorias"] = categorias_oids
            elif isinstance(categorias_raw, str) and categorias_raw.strip():
                # Si viene como string separado por comas
                categorias_oids = []
                for cat_id in categorias_raw.split(','):
                    cat_id = cat_id.strip()
                    if cat_id:
                        try:
                            categorias_oids.append(ObjectId(cat_id))
                        except Exception:
                            pass
                updates["categorias"] = categorias_oids

        if not updates:
            return jsonify({"success": False, "message": "No hay campos para actualizar"}), 400

        GoalModel.update_goal(goal_id, updates)
        updated_goal = GoalModel.get_goal_by_id(goal_id)

        return jsonify({
            "success": True,
            "message": "Objetivo actualizado correctamente",
            "goal": _serialize_goal(updated_goal)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# -------------------------------------------------------------
# GET /goals/user/<user_id>
# Devuelve goals del usuario (HTML o JSON)
# -------------------------------------------------------------
@goal_bp.route("/user/<user_id>", methods=["GET"])
def list_goals_by_user(user_id):
    """Muestra todas las tareas creadas por un usuario especifico."""
    try:
        if user_id == "0":
            user_id = DEFAULT_USER_ID
        goals = GoalModel.get_by_user_id(user_id)
        goals_view = [_serialize_goal(g) for g in goals]
        projects, project_titles = _load_projects()
        categories = _load_categories()
        category_names = _build_category_names(categories)
        if not goals:
            flash("Este usuario aun no tiene objetivos.", "info")
        return render_template(
            "partials/goals_templates/goal_menu.html",
            goals=goals_view,
            projects=projects,
            project_titles=project_titles,
            categories=categories,
            category_names=category_names,
            page="objetivos",
            user_id=user_id
        )

    except Exception as e:
        flash(f"Error al obtener las tareas del usuario: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))
