import json
from datetime import date, datetime, timedelta

from bson import ObjectId

from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel


def _serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def _parse_date_value(value):
    """
    Intenta parsear un valor de fecha a `date`.
    Soporta datetime/date nativos e ISO strings.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        # Caso comun: YYYY-MM-DD
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            pass
        # Caso ISO datetime (incluyendo sufijo Z)
        try:
            normalized = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).date()
        except Exception:
            return None
    return None


def _current_week_bounds(ref_date=None):
    """
    Devuelve rango [lunes, domingo] de la semana actual.
    """
    today = ref_date or date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _is_date_in_week(value, week_start, week_end):
    parsed = _parse_date_value(value)
    if parsed is None:
        return False
    return week_start <= parsed <= week_end


def _load_user_context(user_id):
    tasks = TaskModel.get_task_by_user(user_id)
    goals = GoalModel.get_by_user_id(user_id)
    projects = ProjectModel.get_by_user_id(user_id)
    events = eventModel.get_events_by_user(user_id)

    return {
        "user_id": str(user_id),
        "tasks": [_serialize_value(task) for task in tasks],
        "goals": [_serialize_value(goal) for goal in goals],
        "projects": [_serialize_value(project) for project in projects],
        "events": [_serialize_value(e) for e in events],
    }


def _load_weekly_due_context(user_id, ref_date=None):
    """
    Contexto reducido para weekly_summary:
    solo items con fecha de vencimiento/ocurrencia dentro de la semana actual.
    """
    week_start, week_end = _current_week_bounds(ref_date=ref_date)

    tasks = TaskModel.get_task_by_user(user_id)
    goals = GoalModel.get_by_user_id(user_id)
    projects = ProjectModel.get_by_user_id(user_id)
    events = eventModel.get_events_by_user(user_id)

    tasks_due = [
        task for task in tasks
        if _is_date_in_week(task.get("fecha_limite"), week_start, week_end)
    ]
    goals_due = [
        goal for goal in goals
        if _is_date_in_week(goal.get("fecha_fin"), week_start, week_end)
    ]
    projects_due = [
        project for project in projects
        if _is_date_in_week(project.get("fecha_fin"), week_start, week_end)
    ]
    events_due = [
        e for e in events
        if _is_date_in_week(e.get("fecha_inicio"), week_start, week_end)
        or _is_date_in_week(e.get("fecha_fin"), week_start, week_end)
    ]

    return {
        "user_id": str(user_id),
        "week_range": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
        },
        "tasks_due_this_week": [_serialize_value(task) for task in tasks_due],
        "goals_due_this_week": [_serialize_value(goal) for goal in goals_due],
        "projects_due_this_week": [_serialize_value(project) for project in projects_due],
        "events_this_week": [_serialize_value(e) for e in events_due],
    }


def _load_weekly_planner_context(user_id, ref_date=None):
    """
    Contexto reducido para weekly_planner:
    items con vencimiento/ocurrencia en los proximos 7 dias (incluido hoy).
    """
    start = ref_date or date.today()
    end = start + timedelta(days=6)

    tasks = TaskModel.get_task_by_user(user_id)
    goals = GoalModel.get_by_user_id(user_id)
    projects = ProjectModel.get_by_user_id(user_id)
    events = eventModel.get_events_by_user(user_id)

    tasks_next = [
        task for task in tasks
        if _is_date_in_week(task.get("fecha_limite"), start, end)
    ]
    goals_next = [
        goal for goal in goals
        if _is_date_in_week(goal.get("fecha_fin"), start, end)
    ]
    projects_next = [
        project for project in projects
        if _is_date_in_week(project.get("fecha_fin"), start, end)
    ]
    events_next = [
        e for e in events
        if _is_date_in_week(e.get("fecha_inicio"), start, end)
        or _is_date_in_week(e.get("fecha_fin"), start, end)
    ]

    return {
        "user_id": str(user_id),
        "planning_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "tasks_due_next_7_days": [_serialize_value(task) for task in tasks_next],
        "goals_due_next_7_days": [_serialize_value(goal) for goal in goals_next],
        "projects_due_next_7_days": [_serialize_value(project) for project in projects_next],
        "events_next_7_days": [_serialize_value(e) for e in events_next],
    }


def get_user_context_json(user_id) -> str:
    return json.dumps(_load_user_context(user_id), ensure_ascii=True)


def get_weekly_due_context_json(user_id, ref_date=None) -> str:
    return json.dumps(_load_weekly_due_context(user_id, ref_date=ref_date), ensure_ascii=True)


def get_weekly_planner_context_json(user_id, ref_date=None) -> str:
    return json.dumps(_load_weekly_planner_context(user_id, ref_date=ref_date), ensure_ascii=True)
