"""Dashboard-facing cognitive briefing for GoalMind AI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.emergent_insight_service import analyze_operating_system
from services.heuristics.types import bounded_limit
from services.user_context_service import serialize_value
from services.weekly_planning_service import get_current_week_plan


def _count(findings: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for finding in findings if finding.get("type") == kind)


def _has_insight(insights: list[dict[str, Any]], kind: str) -> bool:
    return any(insight.get("type") == kind for insight in insights)


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(severity, 9)


def _card(
    *,
    kind: str,
    title: str,
    summary: str,
    severity: str,
    cta: str | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": kind,
        "title": title,
        "summary": summary,
        "severity": severity,
        "cta": cta,
        "evidence": evidence or [],
    }


def _assistant_task(
    *,
    kind: str,
    title: str,
    summary: str,
    priority: str,
    source: str,
    suggested_tool: str | None = None,
    suggested_payload: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "type": kind,
        "title": title,
        "summary": summary,
        "priority": priority,
        "source": source,
        "suggested_tool": suggested_tool,
        "suggested_payload": suggested_payload or {},
        "requires_confirmation": requires_confirmation,
    }


def _missing_context(
    findings: list[dict[str, Any]], snapshot: dict[str, Any]
) -> list[dict[str, str]]:
    missing = [
        {
            "field": "weekly_available_hours",
            "label": "Horas utiles disponibles esta semana",
            "why": "Sin capacidad semanal solo puedo estimar sobrecarga por volumen y fechas.",
        },
        {
            "field": "current_energy",
            "label": "Energia actual",
            "why": "La misma lista puede ser viable o inviable segun energia mental disponible.",
        },
        {
            "field": "weekly_top_priorities",
            "label": "Prioridades reales de la semana",
            "why": "Permite comparar atencion real contra intencion declarada.",
        },
    ]
    task_count = snapshot["counts"].get("tasks", 0)
    tasks_without_due = _count(findings, "task_without_due_date")
    if task_count:
        missing.append(
            {
                "field": "estimated_minutes",
                "label": "Duracion estimada de tareas",
                "why": "Es el dato clave para saber si una semana cabe o no cabe.",
            }
        )
    if tasks_without_due:
        missing.append(
            {
                "field": "task_due_dates",
                "label": "Fechas de tareas activas",
                "why": f"Hay {tasks_without_due} tareas sin fecha; cuesta ordenar urgencia.",
            }
        )
    missing.append(
        {
            "field": "blocker_reason",
            "label": "Motivo de bloqueo cuando algo no avanza",
            "why": "Distingue falta de tiempo, falta de claridad, dependencia externa o baja prioridad real.",
        }
    )
    return missing


def _diagnosis(
    *,
    overdue: int,
    due_soon: int,
    pending: int,
    active_projects: int,
    has_planning_debt: bool,
    has_focus_fragmentation: bool,
) -> dict[str, str]:
    if overdue >= 3 or has_planning_debt:
        return {
            "title": "Replanificacion necesaria",
            "severity": "high",
            "summary": "Antes de abrir mas frentes conviene ordenar vencidas, fechas y prioridades.",
        }
    if overdue > 0:
        return {
            "title": "Replanificacion recomendable",
            "severity": "medium",
            "summary": "Hay tareas vencidas; conviene decidir si se hacen, se mueven o se descartan.",
        }
    if pending >= 20 or due_soon >= 5 or has_focus_fragmentation:
        return {
            "title": "Carga alta probable",
            "severity": "medium",
            "summary": "La semana puede estar por encima de capacidad si no se reduce el frente activo.",
        }
    if active_projects >= 5:
        return {
            "title": "Foco disperso",
            "severity": "medium",
            "summary": "Hay varios proyectos activos compitiendo por atencion.",
        }
    return {
        "title": "Sistema operativo estable",
        "severity": "low",
        "summary": "No aparecen senales fuertes de sobrecarga con los datos actuales.",
    }


def _should_start_weekly_planning(
    now: datetime, diagnosis: dict[str, str], overdue: int, due_soon: int
) -> bool:
    early_week = now.weekday() in {0, 1}
    return early_week or diagnosis["severity"] in {"high", "medium"} or overdue > 0 or due_soon >= 3


def build_dashboard_briefing(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int | str | None = 8,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict[str, Any]:
    """Build read-only MCP work items for the initial dashboard."""
    current = now or datetime.utcnow()
    bounded = bounded_limit(limit, default=8, maximum=25)
    analysis = analyze_operating_system(
        usuario_id=usuario_id,
        now=current,
        limit=max(bounded, 20),
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    snapshot = analysis["snapshot"]
    findings = analysis["atomic_findings"]["findings"]
    insights = analysis["emergent_insights"]["insights"]
    counts = snapshot["counts"]

    overdue = _count(findings, "overdue_task")
    due_soon = _count(findings, "due_soon_task")
    goals_without_tasks = _count(findings, "goal_without_tasks")
    tasks_without_due = _count(findings, "task_without_due_date")
    pending = int(counts.get("pending_tasks", 0))
    active_projects = int(counts.get("active_projects", 0))
    has_planning_debt = _has_insight(insights, "planning_debt")
    has_focus_fragmentation = _has_insight(insights, "focus_fragmentation")
    has_operational_drift = _has_insight(insights, "operational_drift")

    diagnosis = _diagnosis(
        overdue=overdue,
        due_soon=due_soon,
        pending=pending,
        active_projects=active_projects,
        has_planning_debt=has_planning_debt,
        has_focus_fragmentation=has_focus_fragmentation,
    )
    planning_state = get_current_week_plan(usuario_id=analysis["user_id"], now=current)
    planning_session = planning_state.get("session")
    should_plan = (
        False
        if planning_session
        else _should_start_weekly_planning(current, diagnosis, overdue, due_soon)
    )

    cards = []
    tasks = []
    if planning_session and planning_session.get("status") in {"active", "ready_for_plan"}:
        cards.append(
            _card(
                kind="weekly_planning_resume",
                title="Planificacion semanal en curso",
                summary="Ya hay una sesion abierta. Conviene terminar las respuestas y generar el plan.",
                severity="medium",
                cta="Continuar planificacion",
                evidence=[
                    f"{len((planning_session.get('answers') or {}))} respuestas guardadas",
                    f"{len(planning_state.get('next_questions') or [])} preguntas pendientes",
                ],
            )
        )
        tasks.append(
            _assistant_task(
                kind="resume_weekly_planning",
                title="Continuar reunion de planificacion semanal",
                summary="Completar datos pendientes y construir el plan de esta semana.",
                priority="media",
                source="dashboard_briefing",
                suggested_tool="answer_weekly_planning_question",
                suggested_payload={"session_id": planning_session.get("_id")},
            )
        )
    elif planning_session and planning_session.get("status") == "planned":
        cards.append(
            _card(
                kind="weekly_plan_ready",
                title="Plan semanal preparado",
                summary="Ya existe un plan para esta semana. Puedes revisarlo o recalcularlo si cambian tus datos.",
                severity="low",
                cta="Revisar plan",
                evidence=["Plan generado", "Sesion semanal activa"],
            )
        )
    elif should_plan:
        cards.append(
            _card(
                kind="weekly_planning",
                title="Reunion semanal recomendada",
                summary="El sistema necesita tus datos de capacidad, energia y prioridades para planificar bien.",
                severity="high" if diagnosis["severity"] == "high" else "medium",
                cta="Planificar semana",
                evidence=[
                    f"{overdue} tareas vencidas",
                    f"{due_soon} tareas próximas",
                    f"{active_projects} proyectos activos",
                ],
            )
        )
        tasks.append(
            _assistant_task(
                kind="start_weekly_planning",
                title="Tener reunion de planificacion semanal",
                summary="Capturar capacidad real, energia, prioridades y criterio de exito.",
                priority="alta" if diagnosis["severity"] == "high" else "media",
                source="dashboard_briefing",
                suggested_tool="start_weekly_planning_session",
                suggested_payload={"period": "current_week"},
            )
        )

    if overdue or due_soon or tasks_without_due:
        cards.append(
            _card(
                kind="replanning",
                title="Replanificacion operativa",
                summary="Hay senales de calendario degradado: vencidas, proximas o tareas sin fecha.",
                severity="high" if overdue >= 3 else "medium",
                cta="Preparar replanteo",
                evidence=[
                    f"{overdue} vencidas",
                    f"{due_soon} proximas",
                    f"{tasks_without_due} sin fecha",
                ],
            )
        )
        tasks.append(
            _assistant_task(
                kind="suggest_replanning",
                title="Proponer que entra esta semana y que se mueve",
                summary="Separar hacer ahora, diferir y revisar/cancelar segun prioridad y fechas.",
                priority="alta" if overdue >= 3 else "media",
                source="dashboard_briefing",
                suggested_tool="suggest_replanning",
                suggested_payload={"horizon_days": 7},
            )
        )

    if has_focus_fragmentation or active_projects > max_active_projects:
        cards.append(
            _card(
                kind="focus",
                title="Reducir frentes abiertos",
                summary="La atencion esta repartida entre demasiados proyectos o tareas pendientes.",
                severity="medium",
                cta="Elegir foco",
                evidence=[
                    f"{active_projects} proyectos activos",
                    f"{pending} tareas pendientes",
                ],
            )
        )
        tasks.append(
            _assistant_task(
                kind="choose_weekly_focus",
                title="Elegir 1-3 prioridades reales",
                summary="Definir que proyectos merecen atencion esta semana y cuales se pausan.",
                priority="media",
                source="dashboard_briefing",
                suggested_tool="prioritize_attention",
                suggested_payload={"max_focus_projects": 3},
            )
        )

    if has_operational_drift or goals_without_tasks:
        cards.append(
            _card(
                kind="execution_gap",
                title="Convertir intencion en acciones",
                summary="Hay objetivos definidos sin suficientes tareas ejecutables.",
                severity="medium",
                cta="Crear siguientes pasos",
                evidence=[f"{goals_without_tasks} objetivos sin tareas"],
            )
        )

    missing_context = _missing_context(findings, snapshot)
    tasks.append(
        _assistant_task(
            kind="collect_missing_context",
            title="Completar datos que faltan para mejores conclusiones",
            summary="Horas disponibles, energia, duracion estimada y prioridades semanales.",
            priority="media",
            source="dashboard_briefing",
            suggested_tool="collect_planning_context",
            suggested_payload={"fields": [item["field"] for item in missing_context[:5]]},
        )
    )
    cards.append(
        _card(
            kind="missing_context",
            title="Datos necesarios para subir de nivel",
            summary="Para decirte si estas cargando demasiado necesito capacidad, energia y estimaciones.",
            severity="info",
            cta="Completar contexto",
            evidence=[item["label"] for item in missing_context[:4]],
        )
    )

    cards.sort(key=lambda item: _severity_rank(item["severity"]))
    tasks.sort(key=lambda item: {"alta": 0, "media": 1, "baja": 2}.get(item["priority"], 9))

    return serialize_value(
        {
            "user_id": analysis["user_id"],
            "generated_at": current,
            "diagnosis": diagnosis,
            "should_start_weekly_planning": should_plan,
            "kpis": {
                "pending_tasks": pending,
                "overdue_tasks": overdue,
                "due_soon_tasks": due_soon,
                "active_projects": active_projects,
                "goals_without_tasks": goals_without_tasks,
            },
            "cards": cards[:bounded],
            "assistant_tasks": tasks[:bounded],
            "missing_context": missing_context,
            "planning_session": {
                "_id": (planning_session or {}).get("_id"),
                "status": (planning_session or {}).get("status"),
                "period_start": (planning_session or {}).get("period_start"),
                "period_end": (planning_session or {}).get("period_end"),
                "has_plan": bool((planning_session or {}).get("generated_plan")),
                "answers_count": len((planning_session or {}).get("answers") or {}),
                "next_questions": planning_state.get("next_questions") or [],
            }
            if planning_session
            else None,
            "source": {
                "atomic_finding_count": analysis["atomic_findings"]["total"],
                "emergent_insight_count": analysis["emergent_insights"]["total"],
                "top_insights": [
                    {
                        "type": insight.get("type"),
                        "title": insight.get("title"),
                        "impact": insight.get("impact"),
                    }
                    for insight in insights[:5]
                ],
            },
        }
    )
