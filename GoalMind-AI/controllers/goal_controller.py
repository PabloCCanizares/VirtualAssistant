# controllers/goal_controller.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from model.goal_model import GoalModel
from model.project_model import ProjectModel

goal_bp = Blueprint("goal_bp", __name__, url_prefix="/goals")


def _serialize_goal(goal):
    goal_view = dict(goal)
    if "_id" in goal_view:
        goal_view["_id"] = str(goal_view["_id"])
    if goal_view.get("project_id"):
        goal_view["project_id"] = str(goal_view["project_id"])
    return goal_view


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

    except Exception as e:
        flash(f"❌ No se pudieron cargar los objetivos: {e}", "danger")
        goals_view = []
        projects, project_titles = [], {}
    return render_template(
        "partials/goals_templates/goal_menu.html",
        goals=goals_view,
        projects=projects,
        project_titles=project_titles,
        selected_category=None,
        page="objetivos",
    )

# -------------------------------------------------------------
# 🔎 FILTRAR POR CATEGORÍA
# -------------------------------------------------------------
@goal_bp.route("/filter", methods=["GET"])
def filter_by_category():
    categoria = (request.args.get("categoria") or "").strip()
    try:
        if categoria:
            goals = GoalModel.find_by_category(categoria)
            flash(f"Filtro aplicado: categoría = {categoria}", "info")
        else:
            goals = GoalModel.get_all_goals()
        goals_view = [_serialize_goal(g) for g in goals]
        projects, project_titles = _load_projects()

    except Exception as e:
        flash(f"❌ Error al filtrar: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))

    return render_template(
        "partials/goals_templates/goal_menu.html",
        goals=goals_view,
        projects=projects,
        project_titles=project_titles,
        selected_category=categoria,
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
            flash("⚠️ Debes seleccionar un proyecto antes de crear un objetivo.", "warning")
            return redirect(url_for("goal_bp.list_goals"))

        data = {
            "id_usuario": request.form.get("id_usuario"),
            "project_id": project_id,
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "categoria": request.form.get("categoria"),
            "progreso": int(request.form.get("progreso") or 0),
            "estado": request.form.get("estado") or "En progreso",
            "prioridad": request.form.get("prioridad") or "Media",
            "scope": request.form.get("scope") or "Personal",
            "alarma_id": request.form.get("alarma_id") or "",
        }

        GoalModel.insert_goal(data)   # 
        flash("✅ Objetivo creado y sincronizado correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al crear el objetivo: {e}", "danger")

    return redirect(url_for("goal_bp.list_goals"))



# -------------------------------------------------------------
# 🔎 VER DETALLE DE UN OBJETIVO
# -------------------------------------------------------------
@goal_bp.route("/<goal_id>", methods=["GET"])
def view_goal(goal_id):
    """Muestra el detalle de un objetivo específico."""
    try:
        goal = GoalModel.get_goal_by_id(goal_id)
        if not goal:
            flash("⚠️ Objetivo no encontrado.", "warning")
            return redirect(url_for("goal_bp.list_goals"))

        goal_view = _serialize_goal(goal)
        projects, project_titles = _load_projects()

        return render_template(
            "partials/goals_templates/goal_detail.html",
            goal=goal_view,
            projects=projects,
            project_titles=project_titles,
            page="objetivos",
        )
    except Exception as e:
        flash(f"❌ Error al cargar el objetivo: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))


# -------------------------------------------------------------
# ✏️ ACTUALIZAR OBJETIVO (edición inline)
# -------------------------------------------------------------
@goal_bp.route("/<goal_id>", methods=["POST"])
def update_goal(goal_id):
    try:
        updates = {
            "titulo": request.form.get("titulo"),
            "descripcion": request.form.get("descripcion"),
            "fecha_inicio": request.form.get("fecha_inicio"),
            "fecha_fin": request.form.get("fecha_fin"),
            "categoria": request.form.get("categoria"),
            "estado": request.form.get("estado"),
            "prioridad": request.form.get("prioridad"),
            "scope": request.form.get("scope"),
            "alarma_id": request.form.get("alarma_id"),
        }
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
        flash("✅ Objetivo actualizado correctamente", "success")
    except Exception as e:
        flash(f"❌ Error al actualizar el objetivo: {e}", "danger")

    return redirect(url_for("goal_bp.list_goals"))

# -------------------------------------------------------------
# 🗑️ ELIMINAR OBJETIVO (individual)
# -------------------------------------------------------------
@goal_bp.route("/delete/<goal_id>", methods=["POST"])
def delete_goal(goal_id):
    try:
        deleted = GoalModel.delete_goal(goal_id)
        if deleted:
            flash("🗑️ Objetivo eliminado correctamente", "success")
        else:
            flash("⚠️ No se encontró el objetivo a eliminar", "warning")
    except Exception as e:
        flash(f"❌ No se pudo eliminar el objetivo: {e}", "danger")
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
        deleted = GoalModel.delete_goals_by_ids(ids)
        flash(f"Se eliminaron {deleted} objetivo(s).", "success")
    except Exception as e:
        flash(f"❌ No se pudieron eliminar los objetivos seleccionados: {e}", "danger")

    return redirect(url_for("goal_bp.list_goals"))

# -------------------------------------------------------------
# GET /goals/user/<user_id>
# Devuelve goals del usuario (HTML o JSON)
# -------------------------------------------------------------
@goal_bp.route("/user/<user_id>", methods=["GET"])
def list_goals_by_user(user_id):
    """Muestra todas las tareas creadas por un usuario específico."""
    try:
        if user_id == "0":  # Cambié 0 por "0" ya que user_id es string
            user_id = "66ffbbbbbbbbbbbbbbbb0100"
        goals = GoalModel.get_by_user_id(user_id)
        goals_view = [_serialize_goal(g) for g in goals]
        projects, project_titles = _load_projects()
        if not goals:
            flash("Este usuario aún no tiene objetivos.", "info")
        return render_template(
            "partials/goals_templates/goal_menu.html",
            goals=goals_view,
            projects=projects,
            project_titles=project_titles,
            page="objetivos",
            user_id=user_id
        )

    except Exception as e:
        flash(f" Error al obtener las tareas del usuario: {e}", "danger")
        return redirect(url_for("goal_bp.list_goals"))
