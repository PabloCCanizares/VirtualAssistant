"""Atomic deterministic heuristics for GoalMind AI."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.heuristics.types import HeuristicContext, HeuristicDefinition, make_finding
from services.user_context_service import (
    GOAL_FIELDS,
    PROJECT_FIELDS,
    TASK_FIELDS,
    doc_id,
    is_archived,
    is_completed,
    item_timestamp,
    parse_datetime,
    public_doc,
    ref_id,
)


def _task_goal_id(task: dict) -> str:
    return ref_id(task.get("objetivo_id") or task.get("goal_id"))


def _task_project_id(task: dict) -> str:
    return ref_id(task.get("project_id"))


def _goal_project_id(goal: dict) -> str:
    return ref_id(goal.get("project_id"))


def _entity(entity_type: str, item: dict, title_field: str) -> dict:
    return {
        "type": entity_type,
        "id": doc_id(item),
        "title": str(item.get(title_field) or item.get("filename") or "Sin titulo"),
    }


def _user_entity(user_id: str) -> dict:
    return {"type": "user", "id": user_id, "title": "Usuario activo"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _priority(value: Any) -> str:
    return _clean(value).lower()


def _is_high_priority(item: dict) -> bool:
    return _priority(item.get("prioridad")) in {
        "alta",
        "alto",
        "high",
        "urgente",
        "critica",
        "crítica",
    }


def _is_low_priority(item: dict) -> bool:
    return _priority(item.get("prioridad")) in {"baja", "bajo", "low"}


def _progress(item: dict) -> float:
    try:
        return float(item.get("progreso") or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_active_project(project: dict) -> bool:
    return not is_completed(project) and not is_archived(project)


def _is_pending_task(task: dict) -> bool:
    return not is_completed(task)


def build_indexes(dataset: dict[str, Any]) -> dict[str, Any]:
    projects = dataset["projects"]
    goals = dataset["goals"]
    tasks = dataset["tasks"]
    documents = dataset["documents"]

    project_by_id = {doc_id(project): project for project in projects}
    goal_by_id = {doc_id(goal): goal for goal in goals}
    goals_by_project: dict[str, list[dict]] = {}
    tasks_by_goal: dict[str, list[dict]] = {}
    tasks_by_project: dict[str, list[dict]] = {}
    documents_by_project: dict[str, list[dict]] = {}

    for goal in goals:
        goals_by_project.setdefault(_goal_project_id(goal), []).append(goal)
    for task in tasks:
        goal_id = _task_goal_id(task)
        if goal_id:
            tasks_by_goal.setdefault(goal_id, []).append(task)
        project_id = _task_project_id(task)
        if project_id:
            tasks_by_project.setdefault(project_id, []).append(task)
    for document in documents:
        documents_by_project.setdefault(ref_id(document.get("project_id")), []).append(document)

    return {
        "project_by_id": project_by_id,
        "goal_by_id": goal_by_id,
        "goals_by_project": goals_by_project,
        "tasks_by_goal": tasks_by_goal,
        "tasks_by_project": tasks_by_project,
        "documents_by_project": documents_by_project,
        "active_projects": [project for project in projects if _is_active_project(project)],
        "pending_tasks": [task for task in tasks if _is_pending_task(task)],
        "completed_tasks": [task for task in tasks if is_completed(task)],
    }


def _goal_activity_at(goal: dict, ctx: HeuristicContext) -> datetime | None:
    timestamps = [item_timestamp(goal)]
    for task in ctx.indexes["tasks_by_goal"].get(doc_id(goal), []):
        timestamps.append(item_timestamp(task))
    parsed = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(parsed) if parsed else None


def _project_activity_at(project: dict, ctx: HeuristicContext) -> datetime | None:
    timestamps = [item_timestamp(project)]
    project_id = doc_id(project)
    project_goals = ctx.indexes["goals_by_project"].get(project_id, [])
    goal_ids = {doc_id(goal) for goal in project_goals}

    for goal in project_goals:
        timestamps.append(item_timestamp(goal))
    for task in ctx.dataset["tasks"]:
        if _task_goal_id(task) in goal_ids or _task_project_id(task) == project_id:
            timestamps.append(item_timestamp(task))
    for document in ctx.indexes["documents_by_project"].get(project_id, []):
        timestamps.append(item_timestamp(document))
    parsed = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(parsed) if parsed else None


def _project_goal_task_counts(project: dict, ctx: HeuristicContext) -> tuple[int, int]:
    project_id = doc_id(project)
    goals = ctx.indexes["goals_by_project"].get(project_id, [])
    goal_ids = {doc_id(goal) for goal in goals}
    task_count = sum(
        1
        for task in ctx.dataset["tasks"]
        if _task_goal_id(task) in goal_ids or _task_project_id(task) == project_id
    )
    return len(goals), task_count


def evaluate_project_without_goals(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for project in ctx.dataset["projects"]:
        if ctx.indexes["goals_by_project"].get(doc_id(project)):
            continue
        findings.append(
            make_finding(
                kind="project_without_goals",
                category="structure",
                severity="high",
                entity=_entity("project", project, "titulo"),
                evidence={"project": public_doc(project, PROJECT_FIELDS)},
                explanation="El proyecto no tiene objetivos asociados.",
                recommendation="Crear al menos un objetivo medible para convertir intención en avance.",
                suggested_tool="create_goal",
                suggested_payload={
                    "project_id": doc_id(project),
                    "titulo": f"Definir avance principal de {_clean(project.get('titulo')) or 'este proyecto'}",
                },
                confidence=0.98,
            )
        )
    return findings


def evaluate_goal_without_tasks(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for goal in ctx.dataset["goals"]:
        if ctx.indexes["tasks_by_goal"].get(doc_id(goal)):
            continue
        findings.append(
            make_finding(
                kind="goal_without_tasks",
                category="structure",
                severity="medium",
                entity=_entity("goal", goal, "titulo"),
                evidence={"goal": public_doc(goal, GOAL_FIELDS)},
                explanation="El objetivo no tiene tareas asociadas.",
                recommendation="Crear una siguiente acción pequeña y concreta.",
                suggested_tool="create_task",
                suggested_payload={
                    "goal_id": doc_id(goal),
                    "contenido": f"Definir siguiente paso para {_clean(goal.get('titulo')) or 'este objetivo'}",
                },
                confidence=0.98,
            )
        )
    return findings


def evaluate_orphan_task(ctx: HeuristicContext) -> list[dict]:
    findings = []
    goal_ids = set(ctx.indexes["goal_by_id"])
    for task in ctx.dataset["tasks"]:
        if not _is_pending_task(task):
            continue
        goal_id = _task_goal_id(task)
        project_id = _task_project_id(task)
        if goal_id and goal_id in goal_ids:
            continue
        if project_id:
            continue
        findings.append(
            make_finding(
                kind="orphan_task",
                category="structure",
                severity="medium",
                entity=_entity("task", task, "contenido"),
                evidence={"task": public_doc(task, TASK_FIELDS), "goal_id": goal_id or None},
                explanation="La tarea no está vinculada a un objetivo conocido.",
                recommendation="Vincularla a un objetivo o crear un objetivo contenedor.",
                suggested_tool="link_task_to_goal",
                suggested_payload={"task_id": doc_id(task), "goal_id": None},
                requires_confirmation=True,
                confidence=0.94,
            )
        )
    return findings


def evaluate_project_tasks_without_goal(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for task in ctx.dataset["tasks"]:
        if not _is_pending_task(task):
            continue
        project_id = _task_project_id(task)
        goal_id = _task_goal_id(task)
        if not project_id or goal_id:
            continue
        if project_id not in ctx.indexes["project_by_id"]:
            continue
        findings.append(
            make_finding(
                kind="project_tasks_without_goal",
                category="structure",
                severity="medium",
                entity=_entity("task", task, "contenido"),
                evidence={"task": public_doc(task, TASK_FIELDS), "project_id": project_id},
                explanation="La tarea pertenece a un proyecto, pero no a un objetivo.",
                recommendation="Conectar la tarea con un objetivo para mejorar trazabilidad y progreso.",
                suggested_tool="link_task_to_goal",
                suggested_payload={
                    "task_id": doc_id(task),
                    "goal_id": None,
                    "project_id": project_id,
                },
                requires_confirmation=True,
                confidence=0.92,
            )
        )
    return findings


def evaluate_overdue_task(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for task in ctx.dataset["tasks"]:
        if not _is_pending_task(task):
            continue
        due_at = parse_datetime(task.get("fecha_limite"))
        if due_at is None or due_at >= ctx.now:
            continue
        findings.append(
            make_finding(
                kind="overdue_task",
                category="time",
                severity="high",
                entity=_entity("task", task, "contenido"),
                evidence={
                    "task": public_doc(task, TASK_FIELDS),
                    "due_at": due_at,
                    "days_overdue": (ctx.now.date() - due_at.date()).days,
                },
                explanation="La tarea tiene una fecha límite vencida y sigue abierta.",
                recommendation="Replanificar la fecha o cerrarla si ya no aplica.",
                suggested_tool="update_task",
                suggested_payload={"task_id": doc_id(task), "estado": "pendiente"},
                requires_confirmation=True,
                confidence=0.96,
            )
        )
    return findings


def evaluate_due_soon_task(ctx: HeuristicContext) -> list[dict]:
    findings = []
    due_soon_days = ctx.parameters["due_soon_days"]
    for task in ctx.dataset["tasks"]:
        if not _is_pending_task(task):
            continue
        due_at = parse_datetime(task.get("fecha_limite"))
        if due_at is None:
            continue
        days_until_due = (due_at.date() - ctx.now.date()).days
        if days_until_due < 0 or days_until_due > due_soon_days:
            continue
        findings.append(
            make_finding(
                kind="due_soon_task",
                category="time",
                severity="medium" if days_until_due > 1 else "high",
                entity=_entity("task", task, "contenido"),
                evidence={
                    "task": public_doc(task, TASK_FIELDS),
                    "due_at": due_at,
                    "days_until_due": days_until_due,
                    "due_soon_days": due_soon_days,
                },
                explanation="La tarea vence pronto.",
                recommendation="Reservar un bloque de avance o confirmar si sigue siendo prioritaria.",
                suggested_tool="update_task",
                suggested_payload={
                    "task_id": doc_id(task),
                    "prioridad": task.get("prioridad") or "alta",
                },
                requires_confirmation=True,
                confidence=0.9,
            )
        )
    return findings


def evaluate_stale_project(ctx: HeuristicContext) -> list[dict]:
    findings = []
    stale_before = ctx.now - timedelta(days=ctx.parameters["stale_days"])
    for project in ctx.dataset["projects"]:
        if not _is_active_project(project):
            continue
        activity_at = _project_activity_at(project, ctx)
        if activity_at is not None and activity_at >= stale_before:
            continue
        findings.append(
            make_finding(
                kind="stale_project",
                category="time",
                severity="low",
                entity=_entity("project", project, "titulo"),
                evidence={
                    "last_activity_at": activity_at,
                    "stale_days": ctx.parameters["stale_days"],
                    "project": public_doc(project, PROJECT_FIELDS),
                },
                explanation="El proyecto activo no muestra actividad reciente.",
                recommendation="Decidir si reactivarlo, archivarlo o crear un siguiente paso.",
                suggested_tool="create_task",
                suggested_payload={
                    "project_id": doc_id(project),
                    "contenido": f"Revisar estado actual de {_clean(project.get('titulo')) or 'este proyecto'}",
                },
                confidence=0.78,
            )
        )
    return findings


def evaluate_stale_goal(ctx: HeuristicContext) -> list[dict]:
    findings = []
    stale_before = ctx.now - timedelta(days=ctx.parameters["stale_days"])
    for goal in ctx.dataset["goals"]:
        if is_completed(goal):
            continue
        activity_at = _goal_activity_at(goal, ctx)
        if activity_at is not None and activity_at >= stale_before:
            continue
        findings.append(
            make_finding(
                kind="stale_goal",
                category="time",
                severity="low",
                entity=_entity("goal", goal, "titulo"),
                evidence={
                    "last_activity_at": activity_at,
                    "stale_days": ctx.parameters["stale_days"],
                    "goal": public_doc(goal, GOAL_FIELDS),
                },
                explanation="El objetivo no muestra actividad reciente.",
                recommendation="Revisar si sigue siendo relevante o necesita una tarea nueva.",
                suggested_tool="create_task",
                suggested_payload={
                    "goal_id": doc_id(goal),
                    "contenido": f"Reactivar {_clean(goal.get('titulo')) or 'este objetivo'}",
                },
                confidence=0.76,
            )
        )
    return findings


def evaluate_overloaded_goal(ctx: HeuristicContext) -> list[dict]:
    findings = []
    threshold = ctx.parameters["overloaded_task_threshold"]
    for goal in ctx.dataset["goals"]:
        pending = [
            task
            for task in ctx.indexes["tasks_by_goal"].get(doc_id(goal), [])
            if _is_pending_task(task)
        ]
        if len(pending) <= threshold:
            continue
        findings.append(
            make_finding(
                kind="overloaded_goal",
                category="load",
                severity="medium",
                entity=_entity("goal", goal, "titulo"),
                evidence={"pending_tasks": len(pending), "threshold": threshold},
                explanation="El objetivo concentra demasiadas tareas pendientes.",
                recommendation="Priorizar, agrupar o posponer tareas para recuperar foco.",
                suggested_tool="suggest_priorities",
                suggested_payload={"goal_id": doc_id(goal)},
                confidence=0.86,
            )
        )
    return findings


def evaluate_too_many_active_projects(ctx: HeuristicContext) -> list[dict]:
    active = ctx.indexes["active_projects"]
    threshold = ctx.parameters["max_active_projects"]
    if len(active) <= threshold:
        return []
    return [
        make_finding(
            kind="too_many_active_projects",
            category="load",
            severity="medium",
            entity=_user_entity(ctx.dataset["user_id"]),
            evidence={
                "active_projects": len(active),
                "threshold": threshold,
                "projects": [public_doc(project, PROJECT_FIELDS) for project in active[:10]],
            },
            explanation="Hay más proyectos activos de los recomendados para mantener foco.",
            recommendation="Elegir pocos proyectos principales y pausar o archivar el resto.",
            suggested_tool="suggest_priorities",
            suggested_payload={"scope": "projects"},
            confidence=0.82,
        )
    ]


def evaluate_too_many_pending_tasks(ctx: HeuristicContext) -> list[dict]:
    pending = ctx.indexes["pending_tasks"]
    threshold = ctx.parameters["max_pending_tasks"]
    if len(pending) <= threshold:
        return []
    return [
        make_finding(
            kind="too_many_pending_tasks",
            category="load",
            severity="medium",
            entity=_user_entity(ctx.dataset["user_id"]),
            evidence={
                "pending_tasks": len(pending),
                "threshold": threshold,
                "sample": [public_doc(task, TASK_FIELDS) for task in pending[:10]],
            },
            explanation="Hay una acumulación alta de tareas abiertas.",
            recommendation="Cerrar, fusionar o replanificar tareas antes de añadir más carga.",
            suggested_tool="suggest_priorities",
            suggested_payload={"scope": "tasks"},
            confidence=0.84,
        )
    ]


def evaluate_priority_mismatch(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for task in ctx.dataset["tasks"]:
        if not _is_pending_task(task) or not _is_low_priority(task):
            continue
        due_at = parse_datetime(task.get("fecha_limite"))
        if due_at is None:
            continue
        days_until_due = (due_at.date() - ctx.now.date()).days
        if days_until_due > ctx.parameters["due_soon_days"]:
            continue
        findings.append(
            make_finding(
                kind="priority_mismatch",
                category="load",
                severity="medium",
                entity=_entity("task", task, "contenido"),
                evidence={
                    "priority": task.get("prioridad"),
                    "due_at": due_at,
                    "days_until_due": days_until_due,
                },
                explanation="La tarea vence pronto, pero está marcada como baja prioridad.",
                recommendation="Revisar prioridad o fecha límite.",
                suggested_tool="update_task",
                suggested_payload={"task_id": doc_id(task), "prioridad": "media"},
                requires_confirmation=True,
                confidence=0.8,
            )
        )
    return findings


def evaluate_untitled_project(ctx: HeuristicContext) -> list[dict]:
    findings = []
    weak_titles = {"", "sin titulo", "sin título", "untitled", "nuevo proyecto"}
    for project in ctx.dataset["projects"]:
        title = _clean(project.get("titulo")).lower()
        if title not in weak_titles:
            continue
        findings.append(
            make_finding(
                kind="untitled_project",
                category="data_quality",
                severity="low",
                entity=_entity("project", project, "titulo"),
                evidence={"project": public_doc(project, PROJECT_FIELDS)},
                explanation="El proyecto tiene un título genérico o vacío.",
                recommendation="Renombrar el proyecto con un nombre reconocible.",
                suggested_tool="update_project",
                suggested_payload={"project_id": doc_id(project), "titulo": "Nuevo nombre"},
                requires_confirmation=True,
                confidence=0.9,
            )
        )
    return findings


def evaluate_missing_project_description(ctx: HeuristicContext) -> list[dict]:
    return [
        make_finding(
            kind="missing_project_description",
            category="data_quality",
            severity="low",
            entity=_entity("project", project, "titulo"),
            evidence={"project": public_doc(project, PROJECT_FIELDS)},
            explanation="El proyecto no tiene descripción.",
            recommendation="Añadir una descripción breve de propósito, alcance y resultado esperado.",
            suggested_tool="update_project",
            suggested_payload={"project_id": doc_id(project), "descripcion": ""},
            requires_confirmation=True,
            confidence=0.86,
        )
        for project in ctx.dataset["projects"]
        if not _clean(project.get("descripcion"))
    ]


def evaluate_missing_goal_description(ctx: HeuristicContext) -> list[dict]:
    return [
        make_finding(
            kind="missing_goal_description",
            category="data_quality",
            severity="low",
            entity=_entity("goal", goal, "titulo"),
            evidence={"goal": public_doc(goal, GOAL_FIELDS)},
            explanation="El objetivo no tiene descripción.",
            recommendation="Añadir criterios de éxito y alcance del objetivo.",
            suggested_tool="update_goal",
            suggested_payload={"goal_id": doc_id(goal), "descripcion": ""},
            requires_confirmation=True,
            confidence=0.84,
        )
        for goal in ctx.dataset["goals"]
        if not _clean(goal.get("descripcion"))
    ]


def evaluate_task_without_priority(ctx: HeuristicContext) -> list[dict]:
    return [
        make_finding(
            kind="task_without_priority",
            category="data_quality",
            severity="low",
            entity=_entity("task", task, "contenido"),
            evidence={"task": public_doc(task, TASK_FIELDS)},
            explanation="La tarea no tiene prioridad definida.",
            recommendation="Asignar prioridad para mejorar planificación.",
            suggested_tool="update_task",
            suggested_payload={"task_id": doc_id(task), "prioridad": "media"},
            requires_confirmation=True,
            confidence=0.82,
        )
        for task in ctx.dataset["tasks"]
        if _is_pending_task(task) and not _clean(task.get("prioridad"))
    ]


def evaluate_task_without_due_date(ctx: HeuristicContext) -> list[dict]:
    return [
        make_finding(
            kind="task_without_due_date",
            category="data_quality",
            severity="low",
            entity=_entity("task", task, "contenido"),
            evidence={"task": public_doc(task, TASK_FIELDS)},
            explanation="La tarea no tiene fecha límite.",
            recommendation="Añadir fecha si la tarea compite por atención esta semana.",
            suggested_tool="update_task",
            suggested_payload={"task_id": doc_id(task), "fecha_limite": None},
            requires_confirmation=True,
            confidence=0.78,
        )
        for task in ctx.dataset["tasks"]
        if _is_pending_task(task) and parse_datetime(task.get("fecha_limite")) is None
    ]


def evaluate_project_low_progress_with_many_tasks(ctx: HeuristicContext) -> list[dict]:
    findings = []
    threshold = ctx.parameters["low_progress_threshold"]
    for project in ctx.dataset["projects"]:
        _, task_count = _project_goal_task_counts(project, ctx)
        if task_count < 5 or _progress(project) > threshold:
            continue
        findings.append(
            make_finding(
                kind="project_low_progress_with_many_tasks",
                category="progress",
                severity="medium",
                entity=_entity("project", project, "titulo"),
                evidence={
                    "progress": _progress(project),
                    "task_count": task_count,
                    "low_progress_threshold": threshold,
                },
                explanation="El proyecto acumula tareas, pero el progreso declarado sigue bajo.",
                recommendation="Revisar si las tareas son demasiado grandes o si el progreso no se está actualizando.",
                suggested_tool="suggest_priorities",
                suggested_payload={"project_id": doc_id(project)},
                confidence=0.78,
            )
        )
    return findings


def evaluate_goal_zero_progress_with_completed_tasks(ctx: HeuristicContext) -> list[dict]:
    findings = []
    for goal in ctx.dataset["goals"]:
        tasks = ctx.indexes["tasks_by_goal"].get(doc_id(goal), [])
        completed = [task for task in tasks if is_completed(task)]
        if not completed or _progress(goal) > 0:
            continue
        findings.append(
            make_finding(
                kind="goal_zero_progress_with_completed_tasks",
                category="progress",
                severity="medium",
                entity=_entity("goal", goal, "titulo"),
                evidence={
                    "progress": _progress(goal),
                    "completed_tasks": len(completed),
                    "total_tasks": len(tasks),
                },
                explanation="El objetivo tiene tareas completadas, pero su progreso sigue a cero.",
                recommendation="Recalcular o actualizar progreso del objetivo.",
                suggested_tool="update_goal",
                suggested_payload={"goal_id": doc_id(goal), "progreso": None},
                requires_confirmation=True,
                confidence=0.88,
            )
        )
    return findings


def evaluate_goal_progress_stale(ctx: HeuristicContext) -> list[dict]:
    findings = []
    stale_before = ctx.now - timedelta(days=ctx.parameters["stale_days"])
    for goal in ctx.dataset["goals"]:
        if _progress(goal) >= 100:
            continue
        updated_at = parse_datetime(goal.get("updated_at"))
        if updated_at is None or updated_at >= stale_before:
            continue
        tasks = ctx.indexes["tasks_by_goal"].get(doc_id(goal), [])
        if not tasks:
            continue
        findings.append(
            make_finding(
                kind="goal_progress_stale",
                category="progress",
                severity="low",
                entity=_entity("goal", goal, "titulo"),
                evidence={
                    "progress": _progress(goal),
                    "updated_at": updated_at,
                    "task_count": len(tasks),
                },
                explanation="El objetivo tiene tareas, pero su progreso no se actualiza desde hace tiempo.",
                recommendation="Revisar progreso y estado del objetivo.",
                suggested_tool="update_goal",
                suggested_payload={"goal_id": doc_id(goal), "progreso": None},
                requires_confirmation=True,
                confidence=0.74,
            )
        )
    return findings


HEURISTICS: list[HeuristicDefinition] = [
    HeuristicDefinition(
        "project_without_goals",
        "Proyecto sin objetivos.",
        "structure",
        "high",
        evaluate_project_without_goals,
    ),
    HeuristicDefinition(
        "goal_without_tasks",
        "Objetivo sin tareas.",
        "structure",
        "medium",
        evaluate_goal_without_tasks,
    ),
    HeuristicDefinition(
        "orphan_task",
        "Tarea sin objetivo ni proyecto.",
        "structure",
        "medium",
        evaluate_orphan_task,
    ),
    HeuristicDefinition(
        "project_tasks_without_goal",
        "Tarea de proyecto sin objetivo.",
        "structure",
        "medium",
        evaluate_project_tasks_without_goal,
    ),
    HeuristicDefinition("overdue_task", "Tarea vencida.", "time", "high", evaluate_overdue_task),
    HeuristicDefinition(
        "due_soon_task", "Tarea que vence pronto.", "time", "medium", evaluate_due_soon_task
    ),
    HeuristicDefinition(
        "stale_project", "Proyecto sin actividad reciente.", "time", "low", evaluate_stale_project
    ),
    HeuristicDefinition(
        "stale_goal", "Objetivo sin actividad reciente.", "time", "low", evaluate_stale_goal
    ),
    HeuristicDefinition(
        "overloaded_goal", "Objetivo sobrecargado.", "load", "medium", evaluate_overloaded_goal
    ),
    HeuristicDefinition(
        "too_many_active_projects",
        "Demasiados proyectos activos.",
        "load",
        "medium",
        evaluate_too_many_active_projects,
    ),
    HeuristicDefinition(
        "too_many_pending_tasks",
        "Demasiadas tareas pendientes.",
        "load",
        "medium",
        evaluate_too_many_pending_tasks,
    ),
    HeuristicDefinition(
        "priority_mismatch",
        "Prioridad incoherente con fechas.",
        "load",
        "medium",
        evaluate_priority_mismatch,
    ),
    HeuristicDefinition(
        "untitled_project",
        "Proyecto sin nombre reconocible.",
        "data_quality",
        "low",
        evaluate_untitled_project,
    ),
    HeuristicDefinition(
        "missing_project_description",
        "Proyecto sin descripcion.",
        "data_quality",
        "low",
        evaluate_missing_project_description,
    ),
    HeuristicDefinition(
        "missing_goal_description",
        "Objetivo sin descripcion.",
        "data_quality",
        "low",
        evaluate_missing_goal_description,
    ),
    HeuristicDefinition(
        "task_without_priority",
        "Tarea sin prioridad.",
        "data_quality",
        "low",
        evaluate_task_without_priority,
    ),
    HeuristicDefinition(
        "task_without_due_date",
        "Tarea sin fecha limite.",
        "data_quality",
        "low",
        evaluate_task_without_due_date,
    ),
    HeuristicDefinition(
        "project_low_progress_with_many_tasks",
        "Proyecto con bajo progreso y muchas tareas.",
        "progress",
        "medium",
        evaluate_project_low_progress_with_many_tasks,
    ),
    HeuristicDefinition(
        "goal_zero_progress_with_completed_tasks",
        "Objetivo con progreso cero pero tareas completadas.",
        "progress",
        "medium",
        evaluate_goal_zero_progress_with_completed_tasks,
    ),
    HeuristicDefinition(
        "goal_progress_stale",
        "Progreso de objetivo sin actualizar.",
        "progress",
        "low",
        evaluate_goal_progress_stale,
    ),
]
