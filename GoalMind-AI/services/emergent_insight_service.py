"""Emergent deterministic insights for GoalMind AI."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.heuristics.registry import run_atomic_findings
from services.heuristics.types import IMPACT_RANK, bounded_limit
from services.user_context_service import (
    DOCUMENT_FIELDS,
    PROJECT_FIELDS,
    build_active_scope,
    doc_id,
    get_user_dataset,
    get_user_snapshot,
    is_completed,
    item_timestamp,
    public_doc,
    ref_id,
    serialize_value,
)


def _finding_groups(findings: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        groups.setdefault(str(finding.get("type")), []).append(finding)
    return groups


def _entities_from(findings: list[dict], *, limit: int = 8) -> list[dict]:
    seen = set()
    entities = []
    for finding in findings:
        entity = finding.get("entity") or {}
        key = (entity.get("type"), entity.get("id"))
        if key in seen:
            continue
        seen.add(key)
        entities.append(entity)
        if len(entities) >= limit:
            break
    return entities


def _evidence(signal: str, findings: list[dict], *, limit: int = 6) -> dict:
    return {
        "signal": signal,
        "count": len(findings),
        "entities": _entities_from(findings, limit=limit),
    }


def _insight(
    *,
    kind: str,
    category: str,
    title: str,
    summary: str,
    evidence: list[dict],
    related_entities: list[dict],
    confidence: float,
    impact: str,
    recommendation: str,
    suggested_actions: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "type": kind,
        "category": category,
        "title": title,
        "summary": summary,
        "evidence": serialize_value(evidence),
        "related_entities": serialize_value(related_entities),
        "confidence": round(float(confidence), 2),
        "impact": impact,
        "recommendation": recommendation,
        "suggested_actions": serialize_value(suggested_actions or []),
    }


def _suggest_create_task(goal_id: str, content: str, priority: str = "media") -> dict:
    return {
        "tool": "create_task",
        "payload": {
            "goal_id": goal_id,
            "contenido": content,
            "estado": "pendiente",
            "prioridad": priority,
        },
        "requires_confirmation": False,
    }


def _task_goal_id(task: dict) -> str:
    return ref_id(task.get("objetivo_id") or task.get("goal_id"))


def _project_task_counts(project: dict, dataset: dict, scope: dict | None = None) -> tuple[int, int, int]:
    active_scope = scope or build_active_scope(dataset)
    project_id = doc_id(project)
    goals = [
        goal for goal in active_scope["goals"] if ref_id(goal.get("project_id")) == project_id
    ]
    goal_ids = {doc_id(goal) for goal in goals}
    tasks = [
        task
        for task in active_scope["tasks"]
        if _task_goal_id(task) in goal_ids or ref_id(task.get("project_id")) == project_id
    ]
    pending = [task for task in tasks if not is_completed(task)]
    return len(goals), len(tasks), len(pending)


def _recent_task_count_for_project(
    project: dict, dataset: dict, *, now: datetime, days: int, scope: dict | None = None
) -> int:
    active_scope = scope or build_active_scope(dataset)
    project_id = doc_id(project)
    since = now - timedelta(days=days)
    goals = [
        goal for goal in active_scope["goals"] if ref_id(goal.get("project_id")) == project_id
    ]
    goal_ids = {doc_id(goal) for goal in goals}
    count = 0
    for task in active_scope["tasks"]:
        if _task_goal_id(task) not in goal_ids and ref_id(task.get("project_id")) != project_id:
            continue
        timestamp = item_timestamp(task)
        if timestamp is not None and timestamp >= since:
            count += 1
    return count


def _find_research_without_execution(
    dataset: dict, now: datetime, scope: dict | None = None
) -> list[dict]:
    active_scope = scope or build_active_scope(dataset)
    insights = []
    for project in active_scope["projects"]:
        project_id = doc_id(project)
        docs = [
            doc for doc in active_scope["documents"] if ref_id(doc.get("project_id")) == project_id
        ]
        notes = project.get("notas") or []
        recent_tasks = _recent_task_count_for_project(
            project, dataset, now=now, days=14, scope=active_scope
        )
        _, total_tasks, pending_tasks = _project_task_counts(project, dataset, scope=active_scope)
        knowledge_signals = len(docs) + len(notes)
        if knowledge_signals < 3 or recent_tasks > 0:
            continue
        insights.append(
            _insight(
                kind="research_without_execution",
                category="execution_pattern",
                title="Investigación sin ejecución visible",
                summary="El proyecto acumula documentos o notas, pero no muestra tareas recientes.",
                evidence=[
                    {
                        "signal": "documents_and_notes",
                        "count": knowledge_signals,
                        "entities": [public_doc(doc, DOCUMENT_FIELDS) for doc in docs[:5]],
                    },
                    {
                        "signal": "recent_tasks",
                        "count": recent_tasks,
                        "entities": [],
                    },
                    {
                        "signal": "task_load",
                        "count": total_tasks,
                        "pending_tasks": pending_tasks,
                    },
                ],
                related_entities=[
                    {"type": "project", "id": project_id, "title": project.get("titulo") or ""}
                ],
                confidence=0.78,
                impact="medium",
                recommendation="Convertir conocimiento acumulado en una tarea ejecutable o una decisión.",
                suggested_actions=[
                    {
                        "tool": "create_task",
                        "payload": {
                            "project_id": project_id,
                            "contenido": f"Convertir notas/documentos de {project.get('titulo') or 'este proyecto'} en siguiente acción",
                            "prioridad": "media",
                        },
                        "requires_confirmation": False,
                    }
                ],
            )
        )
    return insights


def _find_priority_attention_mismatch(
    dataset: dict, now: datetime, stale_days: int, scope: dict | None = None
) -> list[dict]:
    active_scope = scope or build_active_scope(dataset)
    stale_before = now - timedelta(days=stale_days)
    entities = []
    for project in active_scope["projects"]:
        if str(project.get("prioridad") or "").lower() not in {"alta", "high"}:
            continue
        timestamp = item_timestamp(project)
        if timestamp is None or timestamp < stale_before:
            entities.append(
                {"type": "project", "id": doc_id(project), "title": project.get("titulo") or ""}
            )
    for task in active_scope["tasks"]:
        if str(task.get("prioridad") or "").lower() not in {"alta", "high"} or is_completed(task):
            continue
        timestamp = item_timestamp(task)
        if timestamp is None or timestamp < stale_before:
            entities.append(
                {"type": "task", "id": doc_id(task), "title": task.get("contenido") or ""}
            )
    if len(entities) < 2:
        return []
    return [
        _insight(
            kind="priority_attention_mismatch",
            category="attention_pattern",
            title="Prioridad alta sin atención reciente",
            summary="Hay elementos marcados como alta prioridad que no muestran actividad reciente.",
            evidence=[
                {
                    "signal": "high_priority_stale_entities",
                    "count": len(entities),
                    "entities": entities[:8],
                }
            ],
            related_entities=entities[:8],
            confidence=0.8,
            impact="medium",
            recommendation="Revisar si esas prioridades siguen siendo reales o necesitan una acción inmediata.",
            suggested_actions=[
                {
                    "tool": "suggest_priorities",
                    "payload": {"scope": "high_priority_attention"},
                    "requires_confirmation": False,
                }
            ],
        )
    ]


def find_emergent_insights(
    usuario_id: str | None = None,
    *,
    atomic_findings: dict | None = None,
    now: datetime | None = None,
    limit: int | str | None = 20,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    dataset = get_user_dataset(usuario_id=usuario_id)
    active_scope = build_active_scope(dataset)
    atomic = atomic_findings or run_atomic_findings(
        usuario_id=dataset["user_id"],
        now=current,
        limit=500,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    findings = atomic["findings"]
    groups = _finding_groups(findings)
    insights: list[dict] = []

    drift_signals = groups.get("goal_without_tasks", []) + groups.get("stale_project", [])
    if len(groups.get("goal_without_tasks", [])) >= 3 or (
        len(groups.get("goal_without_tasks", [])) >= 2 and groups.get("stale_project")
    ):
        first_goal = groups.get("goal_without_tasks", [{}])[0].get("entity", {})
        insights.append(
            _insight(
                kind="operational_drift",
                category="execution_pattern",
                title="Mucha intención, poca tracción",
                summary="Aparecen objetivos definidos sin tareas y/o proyectos activos sin actividad reciente.",
                evidence=[
                    _evidence("goal_without_tasks", groups.get("goal_without_tasks", [])),
                    _evidence("stale_project", groups.get("stale_project", [])),
                ],
                related_entities=_entities_from(drift_signals, limit=10),
                confidence=0.84,
                impact="high",
                recommendation="Elegir 1-2 objetivos y crear tareas pequeñas de avance esta semana.",
                suggested_actions=[
                    _suggest_create_task(
                        str(first_goal.get("id") or ""),
                        "Definir siguiente paso operativo",
                        priority="media",
                    )
                ]
                if first_goal.get("id")
                else [],
            )
        )

    planning_signals = (
        groups.get("overdue_task", [])
        + groups.get("task_without_due_date", [])
        + groups.get("too_many_pending_tasks", [])
    )
    if len(groups.get("overdue_task", [])) >= 3 or (
        len(groups.get("overdue_task", [])) >= 2
        and len(groups.get("task_without_due_date", [])) >= 3
    ):
        insights.append(
            _insight(
                kind="planning_debt",
                category="planning_pattern",
                title="Deuda de planificación",
                summary="Hay tareas vencidas y/o muchas tareas sin fecha, señal de calendario operativo degradado.",
                evidence=[
                    _evidence("overdue_task", groups.get("overdue_task", [])),
                    _evidence("task_without_due_date", groups.get("task_without_due_date", [])),
                    _evidence("too_many_pending_tasks", groups.get("too_many_pending_tasks", [])),
                ],
                related_entities=_entities_from(planning_signals, limit=10),
                confidence=0.86,
                impact="high",
                recommendation="Hacer una revisión de tareas: cerrar, replanificar o asignar fechas realistas.",
                suggested_actions=[
                    {
                        "tool": "suggest_priorities",
                        "payload": {"scope": "planning_debt"},
                        "requires_confirmation": False,
                    }
                ],
            )
        )

    focus_signals = groups.get("too_many_active_projects", []) + groups.get(
        "too_many_pending_tasks", []
    )
    if groups.get("too_many_active_projects") and groups.get("too_many_pending_tasks"):
        insights.append(
            _insight(
                kind="focus_fragmentation",
                category="focus_pattern",
                title="Foco fragmentado",
                summary="La combinación de muchos proyectos activos y muchas tareas pendientes puede dispersar la atención.",
                evidence=[
                    _evidence(
                        "too_many_active_projects", groups.get("too_many_active_projects", [])
                    ),
                    _evidence("too_many_pending_tasks", groups.get("too_many_pending_tasks", [])),
                ],
                related_entities=_entities_from(focus_signals, limit=10),
                confidence=0.82,
                impact="high",
                recommendation="Reducir el frente activo y escoger pocas prioridades visibles.",
                suggested_actions=[
                    {
                        "tool": "suggest_priorities",
                        "payload": {"scope": "focus"},
                        "requires_confirmation": False,
                    }
                ],
            )
        )

    structure_signals = groups.get("orphan_task", []) + groups.get("project_tasks_without_goal", [])
    if len(structure_signals) >= 2:
        insights.append(
            _insight(
                kind="execution_without_structure",
                category="structure_pattern",
                title="Ejecución sin estructura",
                summary="Hay tareas abiertas desconectadas de objetivos, lo que dificulta leer progreso real.",
                evidence=[
                    _evidence("orphan_task", groups.get("orphan_task", [])),
                    _evidence(
                        "project_tasks_without_goal", groups.get("project_tasks_without_goal", [])
                    ),
                ],
                related_entities=_entities_from(structure_signals, limit=10),
                confidence=0.8,
                impact="medium",
                recommendation="Vincular tareas a objetivos o crear objetivos contenedores.",
                suggested_actions=[
                    {
                        "tool": "link_task_to_goal",
                        "payload": {"task_id": None, "goal_id": None},
                        "requires_confirmation": True,
                    }
                ],
            )
        )

    insights.extend(_find_research_without_execution(dataset, current, scope=active_scope))
    insights.extend(
        _find_priority_attention_mismatch(dataset, current, stale_days, scope=active_scope)
    )
    insights.sort(
        key=lambda insight: (IMPACT_RANK.get(insight["impact"], 9), -insight["confidence"])
    )
    bounded = bounded_limit(limit, default=20, maximum=100)

    return {
        "user_id": dataset["user_id"],
        "generated_at": serialize_value(current),
        "source": {
            "atomic_total": atomic["total"],
            "atomic_counts_by_type": atomic["counts_by_type"],
        },
        "total": len(insights),
        "returned": min(len(insights), bounded),
        "insights": insights[:bounded],
    }


def analyze_operating_system(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int | str | None = 20,
    **parameters,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    snapshot = get_user_snapshot(usuario_id=usuario_id, now=current)
    atomic = run_atomic_findings(usuario_id=usuario_id, now=current, limit=500, **parameters)
    emergent = find_emergent_insights(
        usuario_id=snapshot["user_id"],
        atomic_findings=atomic,
        now=current,
        limit=limit,
        **parameters,
    )

    high_findings = [finding for finding in atomic["findings"] if finding["severity"] == "high"]
    risks = [
        {
            "type": insight["type"],
            "impact": insight["impact"],
            "summary": insight["summary"],
            "related_entities": insight["related_entities"],
        }
        for insight in emergent["insights"]
        if insight["impact"] == "high"
    ]
    risks.extend(
        {
            "type": finding["type"],
            "impact": "medium",
            "summary": finding["explanation"],
            "related_entities": [finding["entity"]],
        }
        for finding in high_findings[:10]
    )

    suggested_actions = []
    for insight in emergent["insights"]:
        suggested_actions.extend(insight.get("suggested_actions") or [])

    return {
        "user_id": snapshot["user_id"],
        "generated_at": serialize_value(current),
        "snapshot": snapshot,
        "atomic_findings": atomic,
        "emergent_insights": emergent,
        "risks": risks[:10],
        "opportunities": [
            {
                "type": "focus_review",
                "summary": "Usar los insights emergentes para elegir prioridades de la semana.",
            }
        ],
        "recommendations": [insight["recommendation"] for insight in emergent["insights"][:5]],
        "suggested_actions": suggested_actions[: bounded_limit(limit, default=20, maximum=100)],
    }


def build_agent_context(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int | str | None = 10,
    **parameters,
) -> dict[str, Any]:
    analysis = analyze_operating_system(usuario_id=usuario_id, now=now, limit=limit, **parameters)
    snapshot = analysis["snapshot"]
    atomic = analysis["atomic_findings"]

    urgent_tasks = [
        finding["evidence"].get("task")
        for finding in atomic["findings"]
        if finding["type"] in {"overdue_task", "due_soon_task"}
    ]
    blocked_goals = [
        finding["entity"]
        for finding in atomic["findings"]
        if finding["type"] in {"goal_without_tasks", "stale_goal", "overloaded_goal"}
    ]

    dataset = get_user_dataset(usuario_id=analysis["user_id"])
    active_scope = build_active_scope(dataset)
    key_projects = sorted(
        active_scope["projects"],
        key=lambda project: (
            0 if str(project.get("prioridad") or "").lower() in {"alta", "high"} else 1,
            str(project.get("titulo") or ""),
        ),
    )[: bounded_limit(limit, default=10, maximum=25)]

    return {
        "identity": {"user_id": analysis["user_id"]},
        "executive_summary": {
            "counts": snapshot["counts"],
            "top_recommendations": analysis["recommendations"][:5],
            "insight_count": analysis["emergent_insights"]["total"],
            "atomic_finding_count": atomic["total"],
        },
        "key_projects": [public_doc(project, PROJECT_FIELDS) for project in key_projects],
        "blocked_goals": blocked_goals[:10],
        "urgent_tasks": [task for task in urgent_tasks if task][:10],
        "documents_and_notes": {
            "recent_activity": snapshot["recent_activity"],
        },
        "patterns": analysis["emergent_insights"]["insights"],
        "possible_actions": analysis["suggested_actions"],
        "safety_constraints": [
            "No exponer secretos, URIs completas ni API keys.",
            "Filtrar siempre por el usuario activo.",
            "No ejecutar acciones destructivas sin confirmacion explicita.",
            "Las sugerencias no modifican la base de datos por si solas.",
        ],
    }
