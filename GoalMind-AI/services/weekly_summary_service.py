"""Deterministic weekly metrics shared by dashboard and weekly summaries."""

from __future__ import annotations

import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from database.mongo_conn import get_app_user_id
from model.daily_metric_model import DailyMetricModel
from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.user_context_service import (
    is_active_goal,
    is_active_project,
    is_completed,
    serialize_value,
)

FOCUS_TERMS = (
    "foco",
    "focus",
    "deep work",
    "trabajo profundo",
    "concentracion",
    "estudio",
    "desarrollo",
    "programar",
    "coding",
)

TIME_LAYERS = {
    "productivo",
    "salud",
    "sueno",
    "mantenimiento",
    "ocio",
    "social",
    "logistica",
}
RECOVERY_LAYERS = {"salud", "sueno", "ocio", "social"}
TIME_LAYER_HINTS = {
    "trabajo": "productivo",
    "estudio": "productivo",
    "tarea": "productivo",
    "reunion": "productivo",
    "entrega": "productivo",
    "formacion": "productivo",
    "foco": "productivo",
    "deporte": "salud",
    "entreno": "salud",
    "gym": "salud",
    "salud": "salud",
    "medico": "salud",
    "terapia": "salud",
    "paseo": "salud",
    "dormir": "sueno",
    "sueno": "sueno",
    "siesta": "sueno",
    "descanso": "sueno",
    "comida": "mantenimiento",
    "comer": "mantenimiento",
    "cocinar": "mantenimiento",
    "compra": "mantenimiento",
    "limpieza": "mantenimiento",
    "recado": "mantenimiento",
    "ocio": "ocio",
    "cine": "ocio",
    "serie": "ocio",
    "lectura": "ocio",
    "hobby": "ocio",
    "social": "social",
    "familia": "social",
    "amigos": "social",
    "celebracion": "social",
    "transporte": "logistica",
    "desplazamiento": "logistica",
    "viaje": "logistica",
    "logistica": "logistica",
}
FOCUS_BLOCK_MINUTES = 60


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = _normalize_text(value)
    if normalized in {"1", "true", "si", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif value is None:
        return None
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None

    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def week_bounds(now: datetime | date | None = None) -> tuple[datetime, datetime]:
    current = _as_datetime(now) or datetime.utcnow()
    start_date = current.date() - timedelta(days=current.weekday())
    start = datetime.combine(start_date, time.min)
    end = datetime.combine(start_date + timedelta(days=6), time.max.replace(microsecond=0))
    return start, end


def _in_range(value: Any, start: datetime, end: datetime) -> bool:
    parsed = _as_datetime(value)
    return bool(parsed and start <= parsed <= end)


def _created_at(item: dict) -> datetime | None:
    for key in ("fecha_creacion", "created_at", "uploaded_at"):
        parsed = _as_datetime(item.get(key))
        if parsed:
            return parsed
    return None


def _completed_at(task: dict) -> datetime | None:
    for key in ("completed_at", "fecha_completado", "completed_on", "updated_at"):
        parsed = _as_datetime(task.get(key))
        if parsed:
            return parsed
    return None


def _event_start(event: dict) -> datetime | None:
    return _as_datetime(event.get("fecha_inicio") or event.get("start"))


def _event_end(event: dict) -> datetime | None:
    return _as_datetime(event.get("fecha_fin") or event.get("end"))


def _overlap_minutes(start: datetime | None, end: datetime | None, window_start: datetime, window_end: datetime) -> int:
    if not start or not end or end <= start:
        return 0
    overlap_start = max(start, window_start)
    overlap_end = min(end, window_end)
    if overlap_end <= overlap_start:
        return 0
    return int((overlap_end - overlap_start).total_seconds() // 60)


def _event_sources(event: dict) -> list[dict]:
    sources = [event]
    for key in ("raw", "extendedProps"):
        nested = event.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return sources


def _event_search_text(event: dict) -> str:
    return " ".join(
        _normalize_text(source.get(key))
        for source in _event_sources(event)
        for key in ("tipo_evento", "titulo", "title", "descripcion", "description")
    )


def _event_layer(event: dict) -> str:
    for source in _event_sources(event):
        explicit = _normalize_text(
            source.get("capa_tiempo")
            or source.get("time_layer")
            or source.get("categoria_tiempo")
        )
        if explicit in TIME_LAYERS:
            return explicit

    haystack = _event_search_text(event)
    for hint, layer in TIME_LAYER_HINTS.items():
        if hint in haystack:
            return layer

    for source in _event_sources(event):
        productive = _coerce_bool(source.get("cuenta_productivo"))
        if productive is True:
            return "productivo"
        if productive is False:
            recovery = _coerce_bool(source.get("cuenta_recuperacion"))
            return "salud" if recovery else "mantenimiento"

    return "productivo"


def _event_counts_productive(event: dict) -> bool:
    for source in _event_sources(event):
        productive = _coerce_bool(source.get("cuenta_productivo"))
        if productive is not None:
            return productive
    return _event_layer(event) == "productivo"


def _event_counts_recovery(event: dict) -> bool:
    for source in _event_sources(event):
        recovery = _coerce_bool(source.get("cuenta_recuperacion"))
        if recovery is not None:
            return recovery
    return _event_layer(event) in RECOVERY_LAYERS


def _is_focus_event(event: dict, minutes: int) -> bool:
    if not _event_counts_productive(event):
        return False
    text = _event_search_text(event)
    return minutes >= FOCUS_BLOCK_MINUTES or any(
        _normalize_text(term) in text for term in FOCUS_TERMS
    )


def _priority(value: Any) -> str:
    raw = str(value or "media").strip().lower()
    if raw in {"alta", "high", "urgent", "urgente", "critica", "critico"}:
        return "alta"
    if raw in {"baja", "low"}:
        return "baja"
    return "media"


def _pct(value: float, total: float) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(round((value / total) * 100))))


def _avg(values: list[float]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return round(sum(cleaned) / len(cleaned), 2) if cleaned else None


def _bar_values(values: list[float], *, minimum: int = 12) -> list[int]:
    highest = max(values) if values else 0
    if highest <= 0:
        return [minimum for _ in values]
    return [max(minimum, min(100, int(round((value / highest) * 100)))) for value in values]


def _metric_float(metric: dict | None, key: str) -> float | None:
    value = (metric or {}).get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_dataset(usuario_id: str) -> dict[str, list[dict]]:
    return {
        "projects": ProjectModel.get_all_projects(usuario_id=usuario_id),
        "goals": GoalModel.get_all_goals(usuario_id=usuario_id),
        "tasks": TaskModel.get_all_tasks(usuario_id=usuario_id),
        "events": eventModel.get_all_events(usuario_id=usuario_id),
        "documents": ProjectDocumentModel.get_all_documents(usuario_id=usuario_id),
    }


def build_weekly_summary_metrics(
    usuario_id: str | None = None,
    *,
    now: datetime | date | None = None,
    dataset: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Build read-only metrics for the current week."""
    user_id = str(usuario_id or get_app_user_id())
    current = _as_datetime(now) or datetime.utcnow()
    week_start, week_end = week_bounds(current)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start - timedelta(seconds=1)
    today_start = datetime.combine(current.date(), time.min)
    today_end = datetime.combine(current.date(), time.max.replace(microsecond=0))
    next_7_end = today_start + timedelta(days=7) - timedelta(seconds=1)
    week_days = [week_start.date() + timedelta(days=index) for index in range(7)]

    source = dataset or _load_dataset(user_id)
    projects = list(source.get("projects") or [])
    goals = list(source.get("goals") or [])
    tasks = list(source.get("tasks") or [])
    events = list(source.get("events") or [])
    documents = list(source.get("documents") or [])
    daily_metrics = list(
        source.get("daily_metrics")
        or DailyMetricModel.get_range(week_start.date(), week_end.date(), usuario_id=user_id)
    )

    pending_tasks = [task for task in tasks if not is_completed(task)]
    completed_tasks = [task for task in tasks if is_completed(task)]
    tasks_due_this_week = [
        task for task in tasks if _in_range(task.get("fecha_limite"), week_start, week_end)
    ]
    pending_due_this_week = [task for task in tasks_due_this_week if not is_completed(task)]
    overdue_tasks = [
        task
        for task in pending_tasks
        if (due_at := _as_datetime(task.get("fecha_limite"))) and due_at < today_start
    ]
    due_today_tasks = [
        task
        for task in pending_tasks
        if (due_at := _as_datetime(task.get("fecha_limite"))) and today_start <= due_at <= today_end
    ]
    due_next_7_tasks = [
        task
        for task in pending_tasks
        if (due_at := _as_datetime(task.get("fecha_limite"))) and today_start <= due_at <= next_7_end
    ]
    completed_this_week = [
        task
        for task in completed_tasks
        if (completed_at := _completed_at(task)) and week_start <= completed_at <= week_end
    ]
    completed_previous_week = [
        task
        for task in completed_tasks
        if (completed_at := _completed_at(task)) and previous_start <= completed_at <= previous_end
    ]
    created_this_week = [
        task for task in tasks if (created := _created_at(task)) and week_start <= created <= week_end
    ]
    tasks_without_due = [task for task in pending_tasks if not _as_datetime(task.get("fecha_limite"))]
    high_priority_pending = [
        task for task in pending_tasks if _priority(task.get("prioridad")) == "alta"
    ]

    completion_by_day = Counter((_completed_at(task) or current).date() for task in completed_this_week)
    due_by_day = Counter(
        _as_datetime(task.get("fecha_limite")).date()
        for task in tasks_due_this_week
        if _as_datetime(task.get("fecha_limite"))
    )

    events_today = []
    events_this_week = []
    focus_events = []
    for event in events:
        start = _event_start(event)
        end = _event_end(event)
        week_minutes = _overlap_minutes(start, end, week_start, week_end)
        if week_minutes:
            events_this_week.append(event)
            if _is_focus_event(event, week_minutes):
                focus_events.append(event)
        if _overlap_minutes(start, end, today_start, today_end):
            events_today.append(event)

    day_event_minutes = []
    day_productive_minutes = []
    day_non_productive_minutes = []
    day_recovery_minutes = []
    day_focus_minutes = []
    layer_minutes_week = Counter()
    for day in week_days:
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max.replace(microsecond=0))
        total_minutes = 0
        productive_minutes = 0
        non_productive_minutes = 0
        recovery_minutes = 0
        focus_minutes = 0

        for event in events:
            minutes = _overlap_minutes(_event_start(event), _event_end(event), day_start, day_end)
            if not minutes:
                continue

            layer = _event_layer(event)
            total_minutes += minutes
            layer_minutes_week[layer] += minutes

            if _event_counts_productive(event):
                productive_minutes += minutes
            else:
                non_productive_minutes += minutes

            if _event_counts_recovery(event):
                recovery_minutes += minutes

            if _is_focus_event(event, minutes):
                focus_minutes += minutes

        day_event_minutes.append(total_minutes)
        day_productive_minutes.append(productive_minutes)
        day_non_productive_minutes.append(non_productive_minutes)
        day_recovery_minutes.append(recovery_minutes)
        day_focus_minutes.append(focus_minutes)

    today_index = current.weekday()
    busy_minutes_today = day_event_minutes[today_index]
    productive_minutes_today = day_productive_minutes[today_index]
    busy_minutes_week = sum(day_event_minutes)
    productive_minutes_week = sum(day_productive_minutes)
    non_productive_minutes_week = sum(day_non_productive_minutes)
    recovery_minutes_week = sum(day_recovery_minutes)
    focus_minutes_week = sum(day_focus_minutes)

    metrics_by_date = {
        str(metric.get("date")): metric for metric in daily_metrics if metric.get("date")
    }
    sleep_values = [_metric_float(metric, "sleep_hours") for metric in daily_metrics]
    mood_values = [_metric_float(metric, "mood_score") for metric in daily_metrics]
    sleep_values = [value for value in sleep_values if value is not None]
    mood_values = [value for value in mood_values if value is not None]
    latest_sleep = next(
        (
            metrics_by_date[key]
            for key in sorted(metrics_by_date.keys(), reverse=True)
            if _metric_float(metrics_by_date[key], "sleep_hours") is not None
        ),
        None,
    )
    latest_mood = next(
        (
            metrics_by_date[key]
            for key in sorted(metrics_by_date.keys(), reverse=True)
            if _metric_float(metrics_by_date[key], "mood_score") is not None
        ),
        None,
    )
    latest_weather = next(
        (
            metrics_by_date[key]
            for key in sorted(metrics_by_date.keys(), reverse=True)
            if (
                _metric_float(metrics_by_date[key], "weather_temp_max_c") is not None
                or _metric_float(metrics_by_date[key], "weather_temp_min_c") is not None
            )
        ),
        None,
    )
    today_metric = metrics_by_date.get(current.date().isoformat())

    sleep_by_day = [
        _metric_float(metrics_by_date.get(day.isoformat()), "sleep_hours") or 0
        for day in week_days
    ]
    mood_by_day = [
        _metric_float(metrics_by_date.get(day.isoformat()), "mood_score") or 0
        for day in week_days
    ]

    risks = []
    if overdue_tasks:
        risks.append(
            {
                "type": "overdue_tasks",
                "severity": "high",
                "label": "Tareas vencidas",
                "detail": f"{len(overdue_tasks)} tareas pendientes ya pasaron su fecha.",
            }
        )
    if len(tasks_without_due) >= 5:
        risks.append(
            {
                "type": "tasks_without_due",
                "severity": "medium",
                "label": "Tareas sin fecha",
                "detail": f"{len(tasks_without_due)} tareas no tienen fecha limite.",
            }
        )
    if productive_minutes_week >= 30 * 60:
        risks.append(
            {
                "type": "calendar_load",
                "severity": "medium",
                "label": "Carga productiva alta",
                "detail": f"{round(productive_minutes_week / 60, 1):g}h productivas esta semana.",
            }
        )
    if not focus_minutes_week and pending_tasks:
        risks.append(
            {
                "type": "no_focus_blocks",
                "severity": "medium",
                "label": "Foco sin bloque",
                "detail": "No hay bloques productivos largos o de foco esta semana.",
            }
        )

    avg_sleep = _avg(sleep_values)
    avg_mood = _avg(mood_values)
    completed_delta = len(completed_this_week) - len(completed_previous_week)

    return serialize_value(
        {
            "user_id": user_id,
            "generated_at": current,
            "week_range": {
                "start": week_start.date().isoformat(),
                "end": week_end.date().isoformat(),
                "today": current.date().isoformat(),
            },
            "tasks": {
                "total": len(tasks),
                "pending": len(pending_tasks),
                "completed_total": len(completed_tasks),
                "created_this_week": len(created_this_week),
                "completed_this_week": len(completed_this_week),
                "completed_previous_week": len(completed_previous_week),
                "completed_delta": completed_delta,
                "due_this_week": len(tasks_due_this_week),
                "pending_due_this_week": len(pending_due_this_week),
                "due_today": len(due_today_tasks),
                "due_next_7_days": len(due_next_7_tasks),
                "overdue": len(overdue_tasks),
                "without_due": len(tasks_without_due),
                "high_priority_pending": len(high_priority_pending),
                "completion_rate": _pct(len(completed_this_week), len(tasks_due_this_week)),
            },
            "projects": {
                "total": len(projects),
                "active": sum(1 for project in projects if is_active_project(project)),
            },
            "goals": {
                "total": len(goals),
                "active": sum(1 for goal in goals if is_active_goal(goal)),
                "due_this_week": sum(
                    1 for goal in goals if _in_range(goal.get("fecha_fin"), week_start, week_end)
                ),
            },
            "events": {
                "today": len(events_today),
                "this_week": len(events_this_week),
                "busy_minutes_today": busy_minutes_today,
                "busy_hours_today": round(busy_minutes_today / 60, 1),
                "busy_minutes_week": busy_minutes_week,
                "busy_hours_week": round(busy_minutes_week / 60, 1),
                "productive_minutes_today": productive_minutes_today,
                "productive_hours_today": round(productive_minutes_today / 60, 1),
                "productive_minutes_week": productive_minutes_week,
                "productive_hours_week": round(productive_minutes_week / 60, 1),
                "non_productive_minutes_week": non_productive_minutes_week,
                "non_productive_hours_week": round(non_productive_minutes_week / 60, 1),
                "recovery_minutes_week": recovery_minutes_week,
                "recovery_hours_week": round(recovery_minutes_week / 60, 1),
                "layer_minutes_week": dict(layer_minutes_week),
                "layer_hours_week": {
                    layer: round(minutes / 60, 1)
                    for layer, minutes in sorted(layer_minutes_week.items())
                },
                "focus_events": len(focus_events),
                "focus_minutes_week": focus_minutes_week,
                "focus_hours_week": round(focus_minutes_week / 60, 1),
                "focus_share": _pct(focus_minutes_week, productive_minutes_week),
            },
            "daily_metrics": {
                "days_with_sleep": len(sleep_values),
                "avg_sleep_hours": avg_sleep,
                "latest_sleep_hours": _metric_float(latest_sleep, "sleep_hours"),
                "latest_sleep_date": (latest_sleep or {}).get("date"),
                "sleep_progress": _pct(avg_sleep or 0, 8),
                "days_with_mood": len(mood_values),
                "avg_mood_score": avg_mood,
                "latest_mood_score": _metric_float(latest_mood, "mood_score"),
                "latest_mood_label": (latest_mood or {}).get("mood_label"),
                "latest_mood_date": (latest_mood or {}).get("date"),
                "mood_progress": _pct(avg_mood or 0, 5),
                "today_temp_max_c": _metric_float(today_metric, "weather_temp_max_c"),
                "today_temp_min_c": _metric_float(today_metric, "weather_temp_min_c"),
                "latest_weather_temp_max_c": _metric_float(latest_weather, "weather_temp_max_c"),
                "latest_weather_temp_min_c": _metric_float(latest_weather, "weather_temp_min_c"),
                "latest_weather_label": (latest_weather or {}).get("weather_label"),
                "latest_weather_date": (latest_weather or {}).get("date"),
            },
            "documents": {
                "total": len(documents),
                "added_this_week": sum(
                    1
                    for document in documents
                    if _in_range(document.get("uploaded_at") or document.get("created_at"), week_start, week_end)
                ),
            },
            "bars": {
                "completed_tasks": _bar_values([completion_by_day.get(day, 0) for day in week_days]),
                "due_tasks": _bar_values([due_by_day.get(day, 0) for day in week_days]),
                "agenda_load": _bar_values(day_event_minutes),
                "event_load": _bar_values(day_productive_minutes),
                "productive_load": _bar_values(day_productive_minutes),
                "non_productive_load": _bar_values(day_non_productive_minutes),
                "recovery_load": _bar_values(day_recovery_minutes),
                "focus_load": _bar_values(day_focus_minutes),
                "sleep": _bar_values(sleep_by_day),
                "mood": _bar_values(mood_by_day),
            },
            "risks": risks[:5],
        }
    )
