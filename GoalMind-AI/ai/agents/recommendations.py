import json
import logging
from datetime import date, datetime, time, timezone
from typing import Any

from langchain_core.messages import SystemMessage

from ai.prompts.recommendations_prompt import RECOMMENDATIONS_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def _load_context(context_json: str) -> dict:
    try:
        context = json.loads(context_json or "{}")
    except Exception:
        return {}
    return context if isinstance(context, dict) else {}


def _as_list(context: dict, key: str) -> list[dict]:
    value = context.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


def _is_completed(item: dict) -> bool:
    status = str(item.get("estado") or "").strip().lower()
    return status in {"completada", "completado", "done", "finalizada", "finalizado"}


def _is_inactive(item: dict) -> bool:
    status = str(item.get("estado") or "").strip().lower()
    return status in {
        "completada",
        "completado",
        "done",
        "finalizada",
        "finalizado",
        "pausada",
        "pausado",
        "paused",
        "en pausa",
        "archivada",
        "archivado",
        "cerrada",
        "cerrado",
    }


def _priority_score(value: Any) -> int:
    priority = str(value or "").strip().lower()
    if priority in {"alta", "high", "urgent", "urgente", "critica", "critico"}:
        return 3
    if priority in {"media", "medium", "normal"}:
        return 2
    if priority in {"baja", "low"}:
        return 1
    return 2


def _priority_label(value: Any) -> str:
    score = _priority_score(value)
    if score >= 3:
        return "alta"
    if score <= 1:
        return "baja"
    return "media"


def _title(item: dict, *keys: str) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return "Sin titulo"


def _days_until(due_at: datetime | None, today: date) -> int | None:
    if due_at is None:
        return None
    return (due_at.date() - today).days


def _due_reason(days: int | None) -> str:
    if days is None:
        return "sin fecha limite registrada"
    if days < 0:
        return f"vencida hace {abs(days)} dias"
    if days == 0:
        return "vence hoy"
    if days == 1:
        return "vence manana"
    return f"vence en {days} dias"


def _task_rank(task: dict, today: date) -> tuple:
    due_at = _as_datetime(task.get("fecha_limite"))
    days = _days_until(due_at, today)
    no_due_penalty = 999 if days is None else days
    overdue_boost = 0 if days is not None and days < 0 else 1
    return (overdue_boost, no_due_penalty, -_priority_score(task.get("prioridad")), _title(task, "contenido"))


def _due_items(
    items: list[dict],
    date_key: str,
    title_key: str,
    today: date,
    *,
    horizon_days: int = 7,
    include_overdue: bool = True,
) -> list[dict]:
    due = []
    for item in items:
        if _is_inactive(item):
            continue
        due_at = _as_datetime(item.get(date_key))
        days = _days_until(due_at, today)
        if days is None or days > horizon_days:
            continue
        if days < 0 and not include_overdue:
            continue
        due.append({
            "title": _title(item, title_key, "titulo", "contenido"),
            "days": days,
            "priority": _priority_score(item.get("prioridad")),
        })
    due.sort(key=lambda item: (item["days"], -item["priority"], item["title"]))
    return due


def _project_risks(projects: list[dict]) -> list[str]:
    risks = []
    for project in projects:
        if _is_inactive(project):
            continue
        try:
            progress = float(project.get("progreso") or 0)
        except (TypeError, ValueError):
            progress = 0
        if progress <= 10:
            risks.append(f"{_title(project, 'titulo')}: progreso muy bajo ({progress:g}%).")
    return risks[:2]


def _build_recommendations_fallback(context_json: str) -> str:
    context = _load_context(context_json)
    tasks = _as_list(context, "tasks")
    projects = _as_list(context, "projects")
    goals = _as_list(context, "goals")
    events = _as_list(context, "events")

    today = datetime.utcnow().date()
    pending_tasks = [task for task in tasks if not _is_completed(task)]
    ranked_tasks = sorted(pending_tasks, key=lambda task: _task_rank(task, today))
    top_tasks = ranked_tasks[:3]
    task_due = _due_items(tasks, "fecha_limite", "contenido", today)
    goal_due = _due_items(goals, "fecha_fin", "titulo", today)
    project_due = _due_items(projects, "fecha_fin", "titulo", today)
    upcoming_events = _due_items(
        events,
        "fecha_inicio",
        "titulo",
        today,
        horizon_days=3,
        include_overdue=False,
    )

    if not any((tasks, projects, goals, events)):
        return (
            "Recomendaciones personales\n\n"
            "1. Top prioridades inmediatas: no tengo contexto suficiente todavia. "
            "Crea al menos una tarea u objetivo con fecha para poder priorizar.\n"
            "2. Riesgos por fechas cercanas: no hay fechas registradas.\n"
            "3. Ideas para esta semana: define 3 tareas accionables, asigna fechas limite y reserva un bloque de foco."
        )

    priority_lines = []
    for task in top_tasks:
        due_at = _as_datetime(task.get("fecha_limite"))
        days = _days_until(due_at, today)
        priority_lines.append(
            "- "
            f"{_title(task, 'contenido')}: prioridad {_priority_label(task.get('prioridad'))}, "
            f"{_due_reason(days)}."
        )

    if not priority_lines:
        active_projects = [project for project in projects if not _is_inactive(project)]
        for project in active_projects[:3]:
            priority_lines.append(
                f"- {_title(project, 'titulo')}: convierte el siguiente avance en una tarea con fecha."
            )

    if not priority_lines:
        priority_lines.append("- No hay tareas o proyectos activos que priorizar ahora mismo.")

    risk_lines = []
    for item in task_due[:3]:
        risk_lines.append(f"- Tarea: {item['title']} ({_due_reason(item['days'])}).")
    for item in goal_due[:2]:
        risk_lines.append(f"- Objetivo: {item['title']} ({_due_reason(item['days'])}).")
    for item in project_due[:2]:
        risk_lines.append(f"- Proyecto: {item['title']} ({_due_reason(item['days'])}).")
    risk_lines.extend(f"- Proyecto: {risk}" for risk in _project_risks(projects))

    if not risk_lines:
        risk_lines.append("- No veo vencimientos cercanos ni riesgos claros en el contexto actual.")

    idea_lines = []
    if task_due:
        idea_lines.append("Cierra primero una tarea que venza hoy o manana antes de abrir trabajo nuevo.")
    elif pending_tasks:
        idea_lines.append("Asigna fecha limite a las tareas pendientes sin fecha para que el sistema pueda priorizarlas mejor.")
    else:
        idea_lines.append("Crea una tarea pequena para mantener traccion esta semana.")

    if upcoming_events:
        idea_lines.append(
            f"Prepara con antelacion el proximo evento: {upcoming_events[0]['title']}."
        )
    else:
        idea_lines.append("Reserva un bloque de 60-90 minutos para foco sin reuniones.")

    if projects:
        idea_lines.append("Elige un proyecto activo y define el siguiente resultado visible.")
    if goals:
        idea_lines.append("Revisa el objetivo con mas urgencia y reduce su siguiente paso a una tarea ejecutable.")

    return "\n".join(
        [
            "Recomendaciones personales",
            "",
            "1. Top prioridades inmediatas:",
            *priority_lines,
            "",
            "2. Riesgos por fechas cercanas:",
            *risk_lines[:5],
            "",
            "3. Ideas realistas para esta semana:",
            *[f"- {idea}" for idea in idea_lines[:4]],
        ]
    )


def recommendations_node(state: AppState, llm) -> AppState:
    context_json = state.get("context_json", "{}")
    messages = [
        SystemMessage(content=RECOMMENDATIONS_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {context_json}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("recommendations_node: error invocando LLM")
        draft = _build_recommendations_fallback(context_json)
    if not (draft or "").strip():
        draft = _build_recommendations_fallback(context_json)
    return {"draft_response": draft}
