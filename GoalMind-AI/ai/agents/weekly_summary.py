import json
import logging

from langchain_core.messages import SystemMessage

from ai.prompts.weekly_summary_prompt import WEEKLY_SUMMARY_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def _load_context(context_json: str) -> dict:
    try:
        context = json.loads(context_json or "{}")
    except Exception:
        return {}
    return context if isinstance(context, dict) else {}


def _section(context: dict, name: str) -> dict:
    value = context.get(name)
    return value if isinstance(value, dict) else {}


def _num(value, default=0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_text(value) -> str:
    return str(int(_num(value)))


def _hours(value) -> str:
    number = _num(value, None)
    if number is None:
        return "dato no registrado"
    return f"{number:g} h"


def _range_label(metrics: dict, context: dict) -> str:
    week_range = _section(metrics, "week_range") or _section(context, "week_range")
    start = week_range.get("start")
    end = week_range.get("end")
    if start and end:
        return f" ({start} a {end})"
    return ""


def _risk_lines(risks) -> list[str]:
    if not isinstance(risks, list):
        return []

    lines = []
    for risk in risks[:3]:
        if not isinstance(risk, dict):
            continue
        label = (risk.get("label") or "Riesgo").strip()
        detail = (risk.get("detail") or "").strip()
        lines.append(f"{label}: {detail}" if detail else label)
    return lines


def _fallback_recommendation(tasks: dict, events: dict, risks: list[str]) -> str:
    overdue = _num(tasks.get("overdue"))
    due_today = _num(tasks.get("due_today"))
    focus_hours = _num(events.get("focus_hours_week"))

    if overdue:
        return "Empieza por limpiar las tareas vencidas antes de asumir trabajo nuevo."
    if due_today:
        return "Reserva el primer bloque disponible para cerrar lo que vence hoy."
    if focus_hours <= 0:
        return "Bloquea al menos una sesion de foco de 60-90 minutos para la prioridad principal."
    if risks:
        return "Elige un riesgo de la lista y conviertelo en una accion concreta con fecha."
    return "Manten una revision breve al inicio del lunes y protege los bloques de foco que ya funcionan."


def _build_metrics_fallback(context_json: str) -> str:
    context = _load_context(context_json)
    metrics = _section(context, "summary_metrics")

    if not metrics:
        return (
            "Resumen semanal: no tengo metricas suficientes para generar un balance completo. "
            "Revisa que haya tareas, eventos u objetivos registrados para esta semana."
        )

    tasks = _section(metrics, "tasks")
    projects = _section(metrics, "projects")
    goals = _section(metrics, "goals")
    events = _section(metrics, "events")
    daily = _section(metrics, "daily_metrics")
    risks = _risk_lines(metrics.get("risks"))

    lines = [
        f"Resumen semanal{_range_label(metrics, context)}",
        "",
        (
            "1. Avances clave: completaste "
            f"{_int_text(tasks.get('completed_this_week'))} tareas esta semana "
            f"({_int_text(tasks.get('completed_delta'))} frente a la semana anterior). "
            f"Tienes {_int_text(projects.get('active'))} proyectos activos y "
            f"{_int_text(goals.get('active'))} objetivos activos."
        ),
        (
            "2. Pendientes importantes: "
            f"{_int_text(tasks.get('pending_due_this_week'))} tareas pendientes vencen esta semana, "
            f"{_int_text(tasks.get('due_today'))} vencen hoy, "
            f"{_int_text(tasks.get('overdue'))} estan vencidas y "
            f"{_int_text(tasks.get('high_priority_pending'))} son de prioridad alta."
        ),
        (
            "3. Agenda y energia: registraste "
            f"{_hours(events.get('busy_hours_week'))} de agenda, "
            f"{_hours(events.get('productive_hours_week'))} productivas y "
            f"{_hours(events.get('focus_hours_week'))} de foco. "
            f"Sueno medio: {_hours(daily.get('avg_sleep_hours'))}; "
            f"animo medio: {daily.get('avg_mood_score') or 'dato no registrado'}."
        ),
    ]

    if risks:
        lines.append("4. Riesgos o bloqueos: " + " | ".join(risks))
    else:
        lines.append("4. Riesgos o bloqueos: no hay riesgos destacados registrados.")

    lines.append("Recomendacion: " + _fallback_recommendation(tasks, events, risks))
    return "\n".join(lines)


def weekly_summary_node(state: AppState, llm) -> AppState:
    context_json = state.get("context_json", "{}")
    messages = [
        SystemMessage(content=WEEKLY_SUMMARY_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {context_json}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("weekly_summary_node: error invocando LLM")
        draft = _build_metrics_fallback(context_json)
    if not (draft or "").strip():
        draft = _build_metrics_fallback(context_json)
    return {"draft_response": draft}
