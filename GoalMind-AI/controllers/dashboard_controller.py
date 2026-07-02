from datetime import datetime, timedelta, timezone

from bson import ObjectId
from flask import Blueprint, jsonify, render_template, request, url_for

from database.mongo_conn import get_app_user_id
from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.dashboard_briefing_service import build_dashboard_briefing
from services.weekly_planning_service import (
    answer_weekly_planning_question,
    build_weekly_plan,
    get_current_week_plan,
    should_start_weekly_planning,
    start_weekly_planning_session,
)

dashboard_bp = Blueprint("dashboard_bp", __name__)
DEFAULT_USER_ID = get_app_user_id()


def _id(value):
    return str(value) if value is not None else ""


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, dict) and "$date" in value:
        raw = value.get("$date")
        if isinstance(raw, (int, float)):
            parsed = datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
        else:
            return _parse_date(raw)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _fmt_time(value):
    date = _parse_date(value)
    return date.strftime("%H:%M") if date else ""


def _fmt_day(value):
    date = _parse_date(value)
    return date.strftime("%d/%m") if date else "Sin fecha"


def _status(value):
    return (value or "").strip().lower()


def _is_done(value):
    return _status(value) in {"completada", "completado", "completed", "done", "finalizada", "finalizado"}


def _is_active(value, default="activo"):
    status = _status(value or default)
    return status not in {"completado", "completada", "completed", "done", "finalizado", "finalizada"}


def _priority(value):
    text = _status(value or "media")
    if text in {"alta", "high", "urgent", "urgente"}:
        return "Alta"
    if text in {"baja", "low"}:
        return "Baja"
    return "Media"


def _priority_rank(value):
    return {"Alta": 3, "Media": 2, "Baja": 1}.get(_priority(value), 2)


def _percent(value):
    try:
        return max(0, min(100, int(round(float(value or 0)))))
    except Exception:
        return 0


def _importance(project):
    try:
        return int(project.get("importancia") or 0)
    except Exception:
        return 0


def _duration_label(start, end):
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if not start_dt or not end_dt or end_dt <= start_dt:
        return ""
    minutes = int((end_dt - start_dt).total_seconds() // 60)
    hours = minutes // 60
    rest = minutes % 60
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def _key(value):
    if isinstance(value, ObjectId):
        return str(value)
    if value is None:
        return ""
    return str(value)


def _load_dashboard_data():
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    try:
        projects = ProjectModel.get_all_projects(usuario_id=DEFAULT_USER_ID)
        goals = GoalModel.get_all_goals(usuario_id=DEFAULT_USER_ID)
        tasks = TaskModel.get_all_tasks(usuario_id=DEFAULT_USER_ID)
        events = eventModel.get_all_events(usuario_id=DEFAULT_USER_ID)
        documents = ProjectDocumentModel.get_all_documents(usuario_id=DEFAULT_USER_ID)
        load_error = None
    except Exception as exc:
        projects, goals, tasks, events, documents = [], [], [], [], []
        load_error = str(exc)

    goals_by_project = {}
    for goal in goals:
        goals_by_project.setdefault(_key(goal.get("project_id")), []).append(goal)

    docs_by_project = {}
    for doc in documents:
        pid = _key(doc.get("project_id"))
        docs_by_project[pid] = docs_by_project.get(pid, 0) + 1

    tasks_by_goal = {}
    for task in tasks:
        gid = task.get("objetivo_id") or task.get("goal_id")
        tasks_by_goal.setdefault(_key(gid), []).append(task)

    active_projects = []
    for project in projects:
        pid = _key(project.get("_id"))
        project_goals = goals_by_project.get(pid, [])
        progress = ProjectModel.calculate_progress_from_goals(project_goals)
        if _is_active(project.get("estado"), default="activo"):
            active_projects.append(
                {
                    "id": pid,
                    "title": project.get("titulo") or "(Sin titulo)",
                    "description": project.get("descripcion") or "Sin descripcion",
                    "status": project.get("estado") or "Activo",
                    "priority": _priority(project.get("prioridad")),
                    "progress": _percent(progress),
                    "goals": len(project_goals),
                    "documents": docs_by_project.get(pid, 0),
                    "importance": _importance(project),
                    "due": _fmt_day(project.get("fecha_fin")),
                    "url": url_for("project_bp.view_project", project_id=pid),
                }
            )
    active_projects.sort(key=lambda item: (item["importance"], item["progress"]), reverse=True)

    goal_rows = []
    for goal in goals:
        gid = _key(goal.get("_id"))
        goal_tasks = tasks_by_goal.get(gid, [])
        if goal_tasks:
            completed = sum(1 for task in goal_tasks if _is_done(task.get("estado")))
            progress = (completed / len(goal_tasks)) * 100
        else:
            progress = goal.get("progreso", 0)
        if _is_active(goal.get("estado"), default="en progreso"):
            goal_rows.append(
                {
                    "id": gid,
                    "title": goal.get("titulo") or "(Sin titulo)",
                    "project_id": _key(goal.get("project_id")),
                    "progress": _percent(progress),
                    "tasks": len(goal_tasks),
                    "deadline": _fmt_day(goal.get("fecha_fin")),
                    "priority": _priority(goal.get("prioridad")),
                    "url": url_for("goal_bp.view_goal", goal_id=gid),
                }
            )
    goal_rows.sort(key=lambda item: (-_priority_rank(item["priority"]), item["progress"]))

    task_rows = []
    for task in tasks:
        if _is_done(task.get("estado")):
            continue
        due = _parse_date(task.get("fecha_limite"))
        is_overdue = bool(due and due.date() < today)
        is_today = bool(due and due.date() == today)
        tid = _id(task.get("_id"))
        task_rows.append(
            {
                "id": tid,
                "title": task.get("contenido") or task.get("titulo") or "(Sin titulo)",
                "state": task.get("estado") or "Pendiente",
                "priority": _priority(task.get("prioridad")),
                "due": due,
                "due_label": "Hoy" if is_today else _fmt_day(due),
                "is_overdue": is_overdue,
                "is_today": is_today,
                "url": url_for("task_bp.view_task", task_id=tid),
            }
        )
    task_rows.sort(
        key=lambda item: (
            not item["is_overdue"],
            not item["is_today"],
            -_priority_rank(item["priority"]),
            item["due"] or datetime.max,
        )
    )

    event_rows = []
    busy_minutes_today = 0
    for event in events:
        start = _parse_date(event.get("fecha_inicio") or event.get("start"))
        end = _parse_date(event.get("fecha_fin") or event.get("end"))
        if start and end and start.date() == today and end > start:
            busy_minutes_today += int((end - start).total_seconds() // 60)
        if start and start.date() >= today:
            event_rows.append(
                {
                    "id": _id(event.get("_id")),
                    "title": event.get("titulo") or event.get("title") or "(Sin titulo)",
                    "type": event.get("tipo_evento") or "evento",
                    "day": "Hoy" if start.date() == today else ("Manana" if start.date() == tomorrow else _fmt_day(start)),
                    "time": _fmt_time(start),
                    "duration": _duration_label(start, end),
                    "start": start,
                    "url": url_for("calendar_bp.calendar_page"),
                }
            )
    event_rows.sort(key=lambda item: item["start"] or datetime.max)

    today_events = [event for event in event_rows if event.get("start") and event["start"].date() == today]
    today_tasks = [task for task in task_rows if task["is_today"]]
    critical_tasks = [task for task in task_rows if task["is_overdue"] or task["priority"] == "Alta"]

    plan_items = []
    for event in today_events[:5]:
        plan_items.append(
            {
                "kind": "Agenda",
                "time": event["time"] or "Hoy",
                "title": event["title"],
                "meta": event["type"],
                "tone": "accent",
                "url": event["url"],
            }
        )
    seen_tasks = set()
    for task in (today_tasks + critical_tasks)[:6]:
        if task["id"] in seen_tasks:
            continue
        seen_tasks.add(task["id"])
        plan_items.append(
            {
                "kind": "Tarea",
                "time": task["due_label"],
                "title": task["title"],
                "meta": task["priority"],
                "tone": "danger" if task["is_overdue"] else "warn",
                "url": task["url"],
            }
        )
    plan_items = plan_items[:8]

    total_tasks = len(tasks)
    done_tasks = sum(1 for task in tasks if _is_done(task.get("estado")))
    total_projects = len(projects)
    active_count = len([project for project in projects if _is_active(project.get("estado"), default="activo")])
    avg_goal_progress = _percent(sum((_percent(goal.get("progreso")) for goal in goals), 0) / len(goals)) if goals else 0
    busy_hours = round(busy_minutes_today / 60, 1)
    done_pct = _percent((done_tasks / total_tasks) * 100) if total_tasks else 0
    active_pct = _percent((active_count / total_projects) * 100) if total_projects else 0
    load_pct = _percent((busy_hours / 8) * 100)

    smart_items = []
    if critical_tasks:
        smart_items.append({"tone": "danger", "label": f"{len(critical_tasks)} tareas piden revision", "detail": "Prioridad alta o vencidas."})
    if today_events:
        smart_items.append({"tone": "accent", "label": f"Proximo: {today_events[0]['title']}", "detail": f"{today_events[0]['time']} - {today_events[0]['type']}"})
    if active_projects:
        slow_project = sorted(active_projects, key=lambda item: (item["progress"], -item["importance"]))[0]
        smart_items.append({"tone": "warn", "label": f"Impulso: {slow_project['title']}", "detail": f"{slow_project['progress']}% de avance."})
    smart_items.append({"tone": "neutral", "label": "Sueno sin registrar", "detail": "Hueco listo para conectar descanso y foco."})

    if critical_tasks:
        main_action = {
            "label": critical_tasks[0]["title"],
            "detail": "Resolver tarea critica",
            "url": critical_tasks[0]["url"],
        }
    elif plan_items:
        main_action = {
            "label": plan_items[0]["title"],
            "detail": f"Continuar con {plan_items[0]['kind'].lower()}",
            "url": plan_items[0]["url"],
        }
    elif active_projects:
        main_action = {
            "label": active_projects[0]["title"],
            "detail": "Revisar avance del proyecto",
            "url": active_projects[0]["url"],
        }
    else:
        main_action = {
            "label": "Planificar el dia",
            "detail": "Crear el primer bloque de trabajo",
            "url": url_for("calendar_bp.calendar_page"),
        }

    alerts = []
    if critical_tasks:
        alerts.append({"tone": "danger", "label": "Riesgo de retraso", "detail": f"{len(critical_tasks)} tareas criticas pendientes."})
    if load_pct >= 60:
        alerts.append({"tone": "warn", "label": "Carga alta", "detail": f"{busy_hours:g}h bloqueadas en agenda hoy."})
    if not alerts:
        alerts.append({"tone": "accent", "label": "Sin alertas fuertes", "detail": "No hay bloqueos criticos detectados."})

    return {
        "load_error": load_error,
        "today_label": now.strftime("%d/%m/%Y"),
        "summary_cards": [
            {"icon": "sun", "label": "Hoy", "value": f"{len(today_events)} ev.", "detail": f"{len(today_tasks)} tareas", "subdetail": f"{done_tasks} completadas", "tone": "accent", "progress": done_pct},
            {"icon": "target", "label": "Foco", "value": "Pend.", "detail": "Tiempo profundo", "subdetail": "Hueco IA", "tone": "violet", "progress": 0},
            {"icon": "pulse", "label": "Carga", "value": f"{load_pct}%", "detail": "Carga mental", "subdetail": f"{busy_hours:g}h agenda", "tone": "warn", "progress": load_pct},
            {"icon": "moon", "label": "Sueno", "value": "Sin dato", "detail": "Anoche", "subdetail": "editable pronto", "tone": "green", "progress": 0},
            {"icon": "alert", "label": "Tareas criticas", "value": str(len(critical_tasks)), "detail": "pendientes", "subdetail": "Vencen hoy" if critical_tasks else "Sin urgencias", "tone": "danger", "progress": min(100, len(critical_tasks) * 25)},
        ],
        "plan_items": plan_items,
        "projects": active_projects[:3],
        "goals": goal_rows[:2],
        "tasks": critical_tasks[:5],
        "events": event_rows[:5],
        "smart_items": smart_items[:5],
        "alerts": alerts[:3],
        "main_action": main_action,
        "stats": [
            {"label": "Tiempo profundo", "period": "Esta semana", "value": "Pend.", "delta": "Hueco IA", "trend": "neutral", "tone": "accent", "progress": 0, "bars": [22, 36, 40, 48, 56, 62, 44]},
            {"label": "Tareas completadas", "period": "Esta semana", "value": str(done_tasks), "delta": f"{done_pct}% del total", "trend": "up", "tone": "green", "progress": done_pct, "bars": [28, 36, 44, 52, 64, 58, 46]},
            {"label": "Productividad", "period": "Global", "value": f"{done_pct}%", "delta": "segun tareas", "trend": "up", "tone": "violet", "progress": done_pct, "bars": [42, 48, 40, 54, 46, 58, 50]},
            {"label": "Carga mental", "period": "Hoy", "value": f"{load_pct}%", "delta": f"{busy_hours:g}h agenda", "trend": "down" if load_pct > 65 else "neutral", "tone": "warn", "progress": load_pct, "bars": [24, 30, 26, 42, 36, 48, max(16, load_pct)]},
            {"label": "Sueno (prom.)", "period": "Ultimos 7 dias", "value": "Sin dato", "delta": "editable pronto", "trend": "neutral", "tone": "violet", "progress": 0, "bars": [36, 42, 46, 52, 48, 44, 40]},
        ],
    }


@dashboard_bp.route("/")
def dashboard():
    return render_template("dashboard.html", page="dashboard", dashboard=_load_dashboard_data())


@dashboard_bp.route("/agenda")
def agenda():
    return render_template("dashboard.html", page="agenda", dashboard=_load_dashboard_data())


@dashboard_bp.route("/objetivos")
def objetivos():
    return render_template("dashboard.html", page="objetivos", dashboard=_load_dashboard_data())


@dashboard_bp.route("/tareas")
def tareas():
    return render_template("dashboard.html", page="tareas", dashboard=_load_dashboard_data())


@dashboard_bp.route("/estadisticas")
def estadisticas():
    return render_template("statistics.html", page="estadisticas")


@dashboard_bp.route("/config")
def config():
    return render_template("dashboard.html", page="config", dashboard=_load_dashboard_data())


@dashboard_bp.route("/api/dashboard/briefing")
def dashboard_briefing():
    briefing = build_dashboard_briefing(usuario_id=str(get_app_user_id()))
    return jsonify(briefing)


@dashboard_bp.route("/api/planning/weekly/should-start")
def weekly_planning_should_start():
    return jsonify(should_start_weekly_planning(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/current")
def weekly_planning_current():
    return jsonify(get_current_week_plan(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/start", methods=["POST"])
def weekly_planning_start():
    return jsonify(start_weekly_planning_session(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/<session_id>/answer", methods=["POST"])
def weekly_planning_answer(session_id):
    payload = request.get_json(silent=True) or {}
    field = payload.get("field")
    value = payload.get("value")
    try:
        result = answer_weekly_planning_question(
            session_id=session_id,
            field=field,
            value=value,
            usuario_id=str(get_app_user_id()),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **result})


@dashboard_bp.route("/api/planning/weekly/<session_id>/plan", methods=["POST"])
def weekly_planning_build_plan(session_id):
    try:
        result = build_weekly_plan(session_id=session_id, usuario_id=str(get_app_user_id()))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **result})
