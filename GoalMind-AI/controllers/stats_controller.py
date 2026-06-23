
# controllers/stats_controller.py
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, render_template

from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.user_context import current_user_id

stats_bp = Blueprint("stats_bp", __name__, url_prefix="/stats")
DEFAULT_USER_ID = current_user_id()

# Palette tomada del dashboard (accent, accent2, good, warn, bad)
PALETTE = {
    "bg": "#0b0f1a",
    "bg2": "#0e1424",
    "text": "#e8f0ff",
    "muted": "#9fb0d7",
    "accent": "#6cf3ff",
    "accent2": "#8b7bff",
    "good": "#37e18f",
    "warn": "#ffcc66",
    "bad": "#ff6b88",
}

def _utc_now():
    return datetime.now(timezone.utc)

def _year_now():
    dt = _utc_now()
    return dt.year

def _parse_date(dt_obj):
    """Convierte cualquier formato de fecha a datetime UTC."""
    if not dt_obj:
        return None
    from datetime import datetime as _dt
    try:
        # Objeto datetime nativo de PyMongo
        if isinstance(dt_obj, _dt):
            d = dt_obj
        # Formato JSON extendido de MongoDB: {"$date": "..."}
        elif isinstance(dt_obj, dict) and "$date" in dt_obj:
            date_val = dt_obj["$date"]
            if isinstance(date_val, (int, float)):
                # Timestamp en milisegundos
                d = _dt.fromtimestamp(date_val / 1000, tz=timezone.utc)
            else:
                d = _dt.fromisoformat(str(date_val).replace("Z", "+00:00"))
        # String ISO
        elif isinstance(dt_obj, str):
            d = _dt.fromisoformat(dt_obj.replace("Z", "+00:00"))
        else:
            return None

        # Normalizar a UTC
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        else:
            d = d.astimezone(timezone.utc)
        return d
    except Exception:
        return None

def _date_to_iso(dt_obj):
    """Convierte fecha a string ISO para serialización JSON."""
    d = _parse_date(dt_obj)
    return d.isoformat() if d else None

def _is_in_ym(dt_obj, year):
    """Verifica si una fecha está en el año/mes especificado."""
    d = _parse_date(dt_obj)
    if not d:
        return False
    return d.year == year

def _load_all_tasks():
    tasks = TaskModel.get_all_tasks(usuario_id=current_user_id())
    out = []
    for t in tasks:
        t = dict(t) if not isinstance(t, dict) else t.copy()
        if "_id" in t and not isinstance(t["_id"], str):
            try:
                t["_id"] = str(t["_id"])
            except Exception:
                pass
        out.append(t)
    return out

# Estadísticas (mismas funciones que antes, pero devolviendo uid y palette)
def stats_tasks_completed_month():
    tasks = _load_all_tasks()
    year = _year_now()
    month_tasks = [t for t in tasks if _is_in_ym(t.get("fecha_limite"), year)]
    total = len(month_tasks)
    completed = sum(1 for t in month_tasks if (t.get("estado") or "").strip().lower() == "completada")
    pct = round((completed / total * 100.0) if total else 0.0, 2)
    return {
        "uid": uuid.uuid4().hex,
        "palette": PALETTE,
        "total": total,
        "completed": completed,
        "percentage_completed": pct,
        "items": month_tasks,
        "meta": {"year": year},
    }

def stats_projects_progress():
    projects = ProjectModel.get_all_projects(usuario_id=current_user_id())
    result = []
    for p in projects:
        pid = p.get("_id")
        if isinstance(pid, dict) and "$oid" in pid:
            pid = pid["$oid"]
        pid_str = str(pid) if pid is not None else None
        goals = GoalModel.get_by_project(pid, usuario_id=current_user_id())
        avg = ProjectModel.calculate_progress_from_goals(goals)
        result.append({
            "project_id": pid_str,
            "titulo": p.get("titulo") or p.get("nombre"),
            "progreso_medio": avg,
            "num_goals": len(goals),
        })
    result.sort(key=lambda x: x["progreso_medio"], reverse=True)
    return {"uid": uuid.uuid4().hex, "palette": PALETTE, "projects": result, "count": len(result)}

def stats_tasks_relevance_month():
    PRIOR_POINTS = {"alta":1, "media":1, "baja":1, "high":1, "medium":1, "low":1}
    tasks = _load_all_tasks()
    year = _year_now()
    def priority_points(t):
        p = (t.get("prioridad") or "").strip().lower()
        return PRIOR_POINTS.get(p, 0)
    total_points = sum(priority_points(t) for t in tasks)
    month_tasks = [t for t in tasks if _is_in_ym(t.get("fecha_limite"), year)]
    month_points = sum(priority_points(t) for t in month_tasks)
    pct = round((month_points / total_points * 100.0) if total_points else 0.0, 2)
    table = [{"id": t.get("_id"), "contenido": t.get("contenido"), "prioridad": t.get("prioridad"),
              "estado": t.get("estado"), "fecha_limite": _date_to_iso(t.get("fecha_limite"))}
             for t in month_tasks]
    return {"uid": uuid.uuid4().hex, "palette": PALETTE, "total_points": total_points,
            "month_points": month_points, "percentage_of_relevance": pct, "month_tasks": table,
            "meta": {"year": year}}

def stats_events_by_type_month():
    raw_events = eventModel.get_all_events(usuario_id=current_user_id())
    all_events = []
    for e in raw_events:
        e = dict(e) if not isinstance(e, dict) else e.copy()
        if "_id" in e and not isinstance(e["_id"], str):
            try:
                e["_id"] = str(e["_id"])
            except Exception:
                pass
        all_events.append(e)
    total = len(all_events)
    counts = {}
    for t in all_events:
        cat = (t.get("tipo_evento") or "sin_tipo").strip()
        counts[cat] = counts.get(cat, 0) + 1
    distribution = [{"tipo": tipo, "count": cnt, "percentage": round((cnt/total*100.0) if total else 0.0,2)}
                    for tipo, cnt in counts.items()]
    distribution.sort(key=lambda x: x["count"], reverse=True)
    return {"uid": uuid.uuid4().hex, "palette": PALETTE, "total": total, "distribution": distribution, "items": all_events}

# Mapa de rutas -> template parcial (autónomo)
_STAT_MAP = {
    "tasks_completed_month": {"fn": stats_tasks_completed_month, "template": "partials/stats_templates/stat_tasks_completed_panel.html", "title": "   Tareas cumplidas (mes actual)"},
    "projects_progress": {"fn": stats_projects_progress, "template": "partials/stats_templates/stat_projects_progress_panel.html", "title": "   Progreso por proyectos"},
    "tasks_relevance": {"fn": stats_tasks_relevance_month, "template": "partials/stats_templates/stat_tasks_relevance_panel.html", "title": "   Relevancia de tareas (este mes)"},
    "events_by_type": {"fn": stats_events_by_type_month, "template": "partials/stats_templates/stat_events_by_type_panel.html", "title": "   Eventos por tipo"},
}

@stats_bp.route("/<stat_name>", methods=["GET"])
def render_stat_block(stat_name: str):
    entry = _STAT_MAP.get(stat_name)
    if not entry:
        return ("Estadística no encontrada.", 404)
    try:
        data = entry["fn"]()
        # title opcional
        return render_template(entry["template"], data=data, title=entry.get("title", stat_name))
    except Exception as e:
        current_app.logger.exception("Error calculando estadística %s: %s", stat_name, e)
        return (f"Error calculando la estadística: {e}", 500)
