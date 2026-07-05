from datetime import datetime, timedelta, timezone

from bson import ObjectId
from flask import Blueprint, jsonify, render_template, request, url_for

from database.mongo_conn import get_app_user_id
from mcp_server import tools as mcp_tools
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
from services.weekly_summary_service import build_weekly_summary_metrics

dashboard_bp = Blueprint("dashboard_bp", __name__)
DEFAULT_USER_ID = get_app_user_id()
MCP_WEEKLY_PLANNING_TOOLS = [
    "get_current_week_plan",
    "should_start_weekly_planning",
    "start_weekly_planning_session",
    "answer_weekly_planning_question",
    "build_weekly_plan",
]


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
    return status not in {
        "completado",
        "completada",
        "completed",
        "done",
        "finalizado",
        "finalizada",
        "pausado",
        "pausada",
        "paused",
        "pause",
        "en pausa",
        "on hold",
        "hold",
        "suspendido",
        "suspendida",
        "archivado",
        "archivada",
        "archivo",
        "cerrado",
        "cerrada",
    }


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


def _num(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _hours_label(value):
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return "Sin dato"
    if hours <= 0:
        return "0h"
    return f"{hours:g}h"


def _delta_label(value):
    amount = _num(value)
    if amount > 0:
        return f"+{amount} vs semana anterior"
    if amount < 0:
        return f"{amount} vs semana anterior"
    return "Sin cambio semanal"


def _mcp_weekly_response(result, *, error_status=400):
    payload = result.get("planning") or {}
    base = {
        "success": bool(result.get("success")),
        "source": "mcp",
        "mcp_tools": MCP_WEEKLY_PLANNING_TOOLS,
    }
    if not result.get("success"):
        return (
            jsonify(
                {
                    **base,
                    "error": result.get("error") or "Error ejecutando herramienta MCP.",
                    "code": result.get("code"),
                }
            ),
            error_status,
        )
    return jsonify({**base, **payload})


def _confidence(value):
    text = _status(value)
    if text in {"high", "alta", "critical", "critica", "critico"}:
        return "Alta"
    if text in {"low", "baja", "info"}:
        return "Baja"
    return "Media"


def _weather_temp_label(daily_metrics):
    today_max = daily_metrics.get("today_temp_max_c")
    today_min = daily_metrics.get("today_temp_min_c")
    max_temp = daily_metrics.get("latest_weather_temp_max_c") or today_max
    min_temp = daily_metrics.get("latest_weather_temp_min_c") or today_min
    try:
        if min_temp is not None and max_temp is not None:
            return f"{float(min_temp):g}/{float(max_temp):g}C"
        if max_temp is not None:
            return f"{float(max_temp):g}C"
    except (TypeError, ValueError):
        pass
    return "Pend."


def _build_operational_brain(
    *,
    now,
    weekly_metrics,
    weekly_tasks,
    weekly_events,
    daily_metrics,
    critical_tasks,
    today_events,
    active_projects,
    goal_rows,
    main_action,
    alerts,
    week_load_pct,
    focus_hours,
    week_productive_hours,
    week_non_productive_hours,
):
    overdue = _num(weekly_tasks.get("overdue"))
    due_today = _num(weekly_tasks.get("due_today"))
    pending = _num(weekly_tasks.get("pending"))
    completion_rate = _num(weekly_tasks.get("completion_rate"))
    focus_events = _num(weekly_events.get("focus_events"))
    sleep_latest = daily_metrics.get("latest_sleep_hours")
    avg_sleep = daily_metrics.get("avg_sleep_hours")
    mood_latest = daily_metrics.get("latest_mood_score")
    weather_label = _weather_temp_label(daily_metrics)

    severity = "low"
    status = "Estable"
    tone = "accent"
    if overdue >= 3 or week_load_pct >= 80:
        severity = "high"
        status = "Riesgo alto"
        tone = "danger"
    elif overdue or week_load_pct >= 60 or pending >= 20:
        severity = "medium"
        status = "Riesgo medio"
        tone = "warn"

    evidence = []
    if critical_tasks:
        evidence.append(f"{len(critical_tasks)} tareas criticas")
    if focus_events:
        evidence.append(f"{focus_events} bloques de foco")
    if due_today:
        evidence.append(f"{due_today} tareas hoy")
    if not evidence:
        evidence.append("Sin bloqueos fuertes")

    diagnostics = [
        {"label": "Carga", "value": f"{week_load_pct}%", "tone": "warn" if week_load_pct >= 60 else "accent"},
        {"label": "Foco", "value": _hours_label(focus_hours), "tone": "violet"},
        {"label": "Sueno", "value": _hours_label(sleep_latest or avg_sleep), "tone": "green"},
        {"label": "Temp", "value": weather_label, "tone": "danger" if "36" in weather_label or "37" in weather_label else "neutral"},
    ]

    insights = []
    if week_load_pct >= 60:
        insights.append(
            {
                "title": "Carga productiva alta",
                "detail": f"{_hours_label(week_productive_hours)} productivas esta semana.",
                "tone": "warn",
                "confidence": "Alta",
            }
        )
    if not focus_events and pending:
        insights.append(
            {
                "title": "Foco sin bloque",
                "detail": "Hay tareas pendientes pero no bloques largos detectados.",
                "tone": "warn",
                "confidence": "Media",
            }
        )
    elif focus_events:
        insights.append(
            {
                "title": "Foco disponible",
                "detail": f"{focus_events} bloques productivos detectados.",
                "tone": "accent",
                "confidence": "Alta",
            }
        )
    if sleep_latest is None:
        insights.append(
            {
                "title": "Sueno sin dato reciente",
                "detail": "Falta descanso para estimar foco y carga real.",
                "tone": "neutral",
                "confidence": "Media",
            }
        )
    elif float(sleep_latest) < 6.5:
        insights.append(
            {
                "title": "Descanso bajo",
                "detail": f"Ultimo registro: {float(sleep_latest):g}h.",
                "tone": "warn",
                "confidence": "Media",
            }
        )
    if weather_label != "Pend.":
        insights.append(
            {
                "title": "Clima a vigilar",
                "detail": f"Temperatura registrada: {weather_label}.",
                "tone": "danger" if "36" in weather_label or "37" in weather_label else "neutral",
                "confidence": "Media",
            }
        )
    if active_projects:
        slow_project = sorted(active_projects, key=lambda item: (item["progress"], -item["importance"]))[0]
        insights.append(
            {
                "title": "Proyecto necesita empuje",
                "detail": f"{slow_project['title']} esta al {slow_project['progress']}%.",
                "tone": "warn",
                "confidence": "Media",
            }
        )

    prepared_actions = [
        {
            "title": main_action["label"],
            "detail": main_action["detail"],
            "tag": "MCP",
            "requires_confirmation": False,
            "url": main_action["url"],
        }
    ]
    if overdue:
        prepared_actions.append(
            {
                "title": "Mover tareas vencidas",
                "detail": f"{overdue} pendientes fuera de fecha.",
                "tag": "confirmar",
                "requires_confirmation": True,
                "url": url_for("task_bp.list_tasks_by_user"),
            }
        )
    if today_events:
        prepared_actions.append(
            {
                "title": "Revisar agenda inmediata",
                "detail": f"Proximo: {today_events[0]['title']}",
                "tag": "agenda",
                "requires_confirmation": False,
                "url": url_for("calendar_bp.calendar_page"),
            }
        )
    if goal_rows:
        prepared_actions.append(
            {
                "title": "Convertir objetivo en paso",
                "detail": f"{goal_rows[0]['title']} necesita accion concreta.",
                "tag": "IA",
                "requires_confirmation": True,
                "url": goal_rows[0]["url"],
            }
        )

    missing_context = []
    if sleep_latest is None:
        missing_context.append("sueno")
    if mood_latest is None:
        missing_context.append("energia")
    missing_context.extend(["prioridades", "duracion tareas"])

    return {
        "status": status,
        "severity": severity,
        "tone": tone,
        "updated_at": now.strftime("%H:%M"),
        "diagnostics": diagnostics,
        "next_action": {
            "label": main_action["label"],
            "detail": "Replanificar antes de abrir nuevos frentes." if severity != "low" else main_action["detail"],
            "evidence": " · ".join(evidence),
            "url": main_action["url"],
        },
        "insights": insights[:3],
        "prepared_actions": prepared_actions[:3],
        "missing_context": list(dict.fromkeys(missing_context))[:5],
        "alerts": alerts[:3],
        "completion_rate": completion_rate,
        "separate_time": _hours_label(week_non_productive_hours),
    }


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

    try:
        weekly_metrics = build_weekly_summary_metrics(
            usuario_id=DEFAULT_USER_ID,
            now=now,
            dataset={
                "projects": projects,
                "goals": goals,
                "tasks": tasks,
                "events": events,
                "documents": documents,
            },
        )
    except Exception as exc:
        weekly_metrics = {}
        load_error = f"{load_error}; metricas semanales: {exc}" if load_error else str(exc)

    weekly_tasks = weekly_metrics.get("tasks") or {}
    weekly_events = weekly_metrics.get("events") or {}
    weekly_daily_metrics = weekly_metrics.get("daily_metrics") or {}
    weekly_bars = weekly_metrics.get("bars") or {}

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
    project_ids = {_key(project.get("_id")) for project in projects}
    active_project_ids = set()
    for project in projects:
        pid = _key(project.get("_id"))
        project_goals = [
            goal
            for goal in goals_by_project.get(pid, [])
            if _is_active(goal.get("estado"), default="en progreso")
        ]
        progress = ProjectModel.calculate_progress_from_goals(project_goals)
        if _is_active(project.get("estado"), default="activo"):
            active_project_ids.add(pid)
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
        goal_project_id = _key(goal.get("project_id"))
        if goal_project_id and goal_project_id in project_ids and goal_project_id not in active_project_ids:
            continue
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
                    "project_id": goal_project_id,
                    "progress": _percent(progress),
                    "tasks": len(goal_tasks),
                    "deadline": _fmt_day(goal.get("fecha_fin")),
                    "priority": _priority(goal.get("prioridad")),
                    "url": url_for("goal_bp.view_goal", goal_id=gid),
                }
            )
    goal_rows.sort(key=lambda item: (-_priority_rank(item["priority"]), item["progress"]))

    goal_ids = {_key(goal.get("_id")) for goal in goals}
    active_goal_ids = {goal["id"] for goal in goal_rows}
    task_rows = []
    for task in tasks:
        task_project_id = _key(task.get("project_id"))
        if task_project_id and task_project_id in project_ids and task_project_id not in active_project_ids:
            continue
        task_goal_id = _key(task.get("objetivo_id") or task.get("goal_id"))
        if task_goal_id and task_goal_id in goal_ids and task_goal_id not in active_goal_ids:
            continue
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
    for event in events:
        start = _parse_date(event.get("fecha_inicio") or event.get("start"))
        end = _parse_date(event.get("fecha_fin") or event.get("end"))
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
    productive_hours_today = float(weekly_events.get("productive_hours_today") or 0)
    busy_hours = round(productive_hours_today, 1)
    done_pct = _percent((done_tasks / total_tasks) * 100) if total_tasks else 0
    load_pct = _percent((busy_hours / 8) * 100)

    completed_week = _num(weekly_tasks.get("completed_this_week"))
    due_week = _num(weekly_tasks.get("due_this_week"))
    due_today = _num(weekly_tasks.get("due_today"))
    overdue_week = _num(weekly_tasks.get("overdue"))
    high_pending = _num(weekly_tasks.get("high_priority_pending"))
    critical_week = len(critical_tasks) or max(overdue_week, high_pending)
    completion_rate = _num(weekly_tasks.get("completion_rate"))
    focus_hours = weekly_events.get("focus_hours_week")
    focus_events = _num(weekly_events.get("focus_events"))
    week_busy_hours = weekly_events.get("busy_hours_week")
    week_productive_hours = weekly_events.get("productive_hours_week")
    week_non_productive_hours = weekly_events.get("non_productive_hours_week")
    week_recovery_hours = weekly_events.get("recovery_hours_week")
    week_load_pct = _percent((float(week_productive_hours or 0) / 40) * 100)
    separate_pct = _percent(
        (float(week_non_productive_hours or 0) / float(week_busy_hours or 0)) * 100
    ) if week_busy_hours else 0

    smart_items = []
    if critical_tasks:
        smart_items.append({"tone": "danger", "label": f"{len(critical_tasks)} tareas piden revision", "detail": "Prioridad alta o vencidas."})
    if today_events:
        smart_items.append({"tone": "accent", "label": f"Proximo: {today_events[0]['title']}", "detail": f"{today_events[0]['time']} - {today_events[0]['type']}"})
    if active_projects:
        slow_project = sorted(active_projects, key=lambda item: (item["progress"], -item["importance"]))[0]
        smart_items.append({"tone": "warn", "label": f"Impulso: {slow_project['title']}", "detail": f"{slow_project['progress']}% de avance."})
    if float(week_non_productive_hours or 0) > 0:
        smart_items.append(
            {
                "tone": "neutral",
                "label": f"Separado: {_hours_label(week_non_productive_hours)} no productivas",
                "detail": "Sueno, salud, comida y logistica no suman a foco.",
            }
        )

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
    for risk in (weekly_metrics.get("risks") or [])[:2]:
        tone = "danger" if risk.get("severity") == "high" else "warn"
        alerts.append({"tone": tone, "label": risk.get("label"), "detail": risk.get("detail")})
    if critical_tasks:
        alerts.append({"tone": "danger", "label": "Riesgo de retraso", "detail": f"{len(critical_tasks)} tareas criticas pendientes."})
    if load_pct >= 60:
        alerts.append({"tone": "warn", "label": "Carga productiva alta", "detail": f"{busy_hours:g}h productivas hoy."})
    if not alerts:
        alerts.append({"tone": "accent", "label": "Sin alertas fuertes", "detail": "No hay bloqueos criticos detectados."})

    operational_brain = _build_operational_brain(
        now=now,
        weekly_metrics=weekly_metrics,
        weekly_tasks=weekly_tasks,
        weekly_events=weekly_events,
        daily_metrics=weekly_daily_metrics,
        critical_tasks=critical_tasks,
        today_events=today_events,
        active_projects=active_projects,
        goal_rows=goal_rows,
        main_action=main_action,
        alerts=alerts,
        week_load_pct=week_load_pct,
        focus_hours=focus_hours,
        week_productive_hours=week_productive_hours,
        week_non_productive_hours=week_non_productive_hours,
    )

    default_bars = [18, 24, 32, 28, 42, 36, 30]
    today_bars = weekly_bars.get("agenda_load") or weekly_bars.get("due_tasks") or default_bars
    focus_bars = weekly_bars.get("focus_load") or default_bars
    load_bars = weekly_bars.get("productive_load") or weekly_bars.get("event_load") or default_bars
    separate_bars = weekly_bars.get("non_productive_load") or weekly_bars.get("recovery_load") or default_bars
    critical_bars = weekly_bars.get("due_tasks") or weekly_bars.get("completed_tasks") or default_bars

    return {
        "load_error": load_error,
        "today_label": now.strftime("%d/%m/%Y"),
        "weekly_metrics": weekly_metrics,
        "operational_brain": operational_brain,
        "summary_cards": [
            {"icon": "sun", "label": "Hoy", "value": f"{len(today_events)} ev.", "detail": f"{due_today} tareas", "subdetail": f"{completed_week} comp. semana", "tone": "accent", "progress": completion_rate or done_pct, "bars": today_bars},
            {"icon": "target", "label": "Foco", "value": _hours_label(focus_hours), "detail": "Tiempo profundo", "subdetail": f"{focus_events} bloques prod.", "tone": "violet", "progress": _num(weekly_events.get("focus_share")), "bars": focus_bars},
            {"icon": "pulse", "label": "Carga", "value": f"{week_load_pct}%", "detail": "Carga productiva", "subdetail": f"{_hours_label(week_productive_hours)} productivas", "tone": "warn", "progress": week_load_pct, "bars": load_bars},
            {"icon": "moon", "label": "No productivo", "value": _hours_label(week_non_productive_hours), "detail": "Fuera del foco", "subdetail": "sueno, salud, comida", "tone": "green", "progress": separate_pct, "bars": separate_bars},
            {"icon": "alert", "label": "Tareas criticas", "value": str(critical_week), "detail": "pendientes", "subdetail": f"{overdue_week} vencidas" if overdue_week else "Sin vencidas", "tone": "danger", "progress": min(100, critical_week * 25), "bars": critical_bars},
        ],
        "plan_items": plan_items,
        "projects": active_projects[:3],
        "goals": goal_rows[:3],
        "tasks": critical_tasks[:5],
        "events": event_rows[:5],
        "smart_items": smart_items[:5],
        "alerts": alerts[:3],
        "main_action": main_action,
        "stats": [
            {"label": "Tiempo profundo", "period": "Esta semana", "value": _hours_label(focus_hours), "delta": f"{focus_events} bloques detectados", "trend": "up" if focus_events else "neutral", "tone": "accent", "progress": _num(weekly_events.get("focus_share")), "bars": weekly_bars.get("focus_load") or [12, 12, 12, 12, 12, 12, 12]},
            {"label": "Tareas completadas", "period": "Esta semana", "value": str(completed_week), "delta": _delta_label(weekly_tasks.get("completed_delta")), "trend": "up" if _num(weekly_tasks.get("completed_delta")) > 0 else "neutral", "tone": "green", "progress": completion_rate, "bars": weekly_bars.get("completed_tasks") or [12, 12, 12, 12, 12, 12, 12]},
            {"label": "Cumplimiento", "period": "Semana actual", "value": f"{completion_rate}%", "delta": f"{completed_week}/{due_week} tareas con fecha", "trend": "up" if completion_rate >= 60 else "neutral", "tone": "violet", "progress": completion_rate, "bars": weekly_bars.get("due_tasks") or [12, 12, 12, 12, 12, 12, 12]},
            {"label": "Carga productiva", "period": "Agenda", "value": f"{week_load_pct}%", "delta": f"{_hours_label(week_productive_hours)} productivas", "trend": "down" if week_load_pct > 75 else "neutral", "tone": "warn", "progress": week_load_pct, "bars": weekly_bars.get("productive_load") or weekly_bars.get("event_load") or [12, 12, 12, 12, 12, 12, 12]},
            {"label": "Tiempo separado", "period": "No productivo", "value": _hours_label(week_non_productive_hours), "delta": f"{_hours_label(week_recovery_hours)} recuperacion", "trend": "neutral", "tone": "violet", "progress": separate_pct, "bars": weekly_bars.get("non_productive_load") or [12, 12, 12, 12, 12, 12, 12]},
        ],
    }


@dashboard_bp.route("/")
def dashboard():
    return render_template("dashboard.html", page="dashboard", dashboard=_load_dashboard_data())


@dashboard_bp.route("/reunion-semanal")
def weekly_meeting():
    return render_template("weekly_meeting.html", page="dashboard", dashboard=_load_dashboard_data())


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
    return render_template("config.html", page="config")


@dashboard_bp.route("/api/dashboard/briefing")
def dashboard_briefing():
    briefing = build_dashboard_briefing(usuario_id=str(get_app_user_id()))
    return jsonify(briefing)


@dashboard_bp.route("/api/dashboard/summary")
def dashboard_summary():
    dashboard_data = _load_dashboard_data()
    return jsonify(
        {
            "load_error": dashboard_data.get("load_error"),
            "today_label": dashboard_data.get("today_label"),
            "summary_cards": dashboard_data.get("summary_cards") or [],
            "stats": dashboard_data.get("stats") or [],
            "alerts": dashboard_data.get("alerts") or [],
            "operational_brain": dashboard_data.get("operational_brain") or {},
            "weekly_metrics": dashboard_data.get("weekly_metrics") or {},
        }
    )


@dashboard_bp.route("/api/mcp/planning/weekly/current")
def mcp_weekly_planning_current():
    return _mcp_weekly_response(mcp_tools.get_current_week_plan())


@dashboard_bp.route("/api/mcp/planning/weekly/should-start")
def mcp_weekly_planning_should_start():
    return _mcp_weekly_response(mcp_tools.should_start_weekly_planning())


@dashboard_bp.route("/api/mcp/planning/weekly/start", methods=["POST"])
def mcp_weekly_planning_start():
    return _mcp_weekly_response(mcp_tools.start_weekly_planning_session())


@dashboard_bp.route("/api/mcp/planning/weekly/<session_id>/answer", methods=["POST"])
def mcp_weekly_planning_answer(session_id):
    payload = request.get_json(silent=True) or {}
    return _mcp_weekly_response(
        mcp_tools.answer_weekly_planning_question(
            session_id=session_id,
            field=payload.get("field"),
            value=payload.get("value"),
        )
    )


@dashboard_bp.route("/api/mcp/planning/weekly/<session_id>/plan", methods=["POST"])
def mcp_weekly_planning_build_plan(session_id):
    return _mcp_weekly_response(mcp_tools.build_weekly_plan(session_id=session_id))


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
