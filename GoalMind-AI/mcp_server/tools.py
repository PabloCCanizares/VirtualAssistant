"""Pure MCP tool handlers for GoalMind AI.

These functions intentionally avoid Flask controllers/templates. They call the
same domain models the web app uses and always scope reads/writes to
``get_app_user_id()``.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from typing import Any
from uuid import uuid4

from bson import ObjectId

from database.mongo_conn import (
    ensure_remote_connection,
    flush_deletion_queue,
    get_app_user_id,
    get_local_database,
    get_remote_database,
    sync_all_collections,
    sync_local_to_remote,
)
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.dashboard_briefing_service import build_dashboard_briefing
from services.emergent_insight_service import (
    analyze_operating_system as build_operating_system_analysis,
)
from services.emergent_insight_service import (
    build_agent_context as build_context_for_agent,
)
from services.emergent_insight_service import (
    find_emergent_insights as detect_emergent_insights,
)
from services.heuristics.registry import explain_heuristic as describe_heuristic
from services.heuristics.registry import list_heuristics as list_registered_heuristics
from services.operating_map_service import build_operating_map
from services.operating_profile_service import build_operating_profile
from services.pattern_detection_service import (
    find_atomic_findings as detect_atomic_findings,
)
from services.pattern_detection_service import (
    find_bottlenecks as detect_bottlenecks,
)
from services.portfolio_analysis_service import suggest_next_actions as build_next_actions
from services.user_context_service import (
    get_project_context as build_project_context,
)
from services.user_context_service import (
    get_user_snapshot as build_user_snapshot,
)
from services.weekly_planning_service import (
    answer_weekly_planning_question as save_weekly_planning_answer,
)
from services.weekly_planning_service import (
    build_weekly_plan as build_plan_for_week,
)
from services.weekly_planning_service import (
    get_current_week_plan as fetch_current_week_plan,
)
from services.weekly_planning_service import (
    should_start_weekly_planning as assess_weekly_planning_need,
)
from services.weekly_planning_service import (
    start_weekly_planning_session as create_weekly_planning_session,
)

MAX_LIST_LIMIT = 200

PROJECT_FIELDS = (
    "_id",
    "titulo",
    "descripcion",
    "estado",
    "prioridad",
    "progreso",
    "fecha_inicio",
    "fecha_fin",
    "created_at",
    "updated_at",
    "notas",
)

TASK_FIELDS = (
    "_id",
    "contenido",
    "descripcion",
    "estado",
    "prioridad",
    "fecha_limite",
    "objetivo_id",
    "goal_id",
    "project_id",
    "fecha_creacion",
    "updated_at",
)

GOAL_FIELDS = (
    "_id",
    "titulo",
    "descripcion",
    "estado",
    "prioridad",
    "progreso",
    "project_id",
    "fecha_inicio",
    "fecha_fin",
    "created_at",
    "updated_at",
)

DOCUMENT_FIELDS = (
    "_id",
    "original_name",
    "filename",
    "project_id",
    "goal_id",
    "content_type",
    "uploaded_at",
    "updated_at",
    "remote_sync_pending",
)


def _serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _public_doc(doc: dict | None, fields: tuple[str, ...]) -> dict | None:
    if not doc:
        return None
    return {field: _serialize(doc[field]) for field in fields if field in doc}


def _ok(**payload: Any) -> dict:
    return {"success": True, **payload}


def _error(message: str, *, code: str = "invalid_request", **payload: Any) -> dict:
    return {"success": False, "error": message, "code": code, **payload}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_limit(limit: int | str | None) -> int:
    try:
        parsed = int(limit) if limit is not None else 50
    except (TypeError, ValueError):
        parsed = 50
    return max(1, min(parsed, MAX_LIST_LIMIT))


def _parse_object_id(value: Any, field_name: str) -> ObjectId | None:
    raw = _clean_text(value)
    if not raw:
        return None
    if not ObjectId.is_valid(raw):
        raise ValueError(f"{field_name} no es un ObjectId valido")
    return ObjectId(raw)


def _capture_model_stdout(func, *args, **kwargs):
    buffer = StringIO()
    with redirect_stdout(buffer):
        return func(*args, **kwargs)


def get_active_user() -> dict:
    """Return the exact user id used by the app domain layer."""
    user_id = str(get_app_user_id())
    local_db = get_local_database()
    remote_db = get_remote_database()
    return _ok(
        user_id=user_id,
        storage={
            "local_db_configured": local_db is not None,
            "remote_db_configured": remote_db is not None,
        },
    )


def list_projects(limit: int | str | None = 50, search: str | None = None) -> dict:
    """List projects for the active user only."""
    user_id = str(get_app_user_id())
    projects = ProjectModel.get_all_projects(usuario_id=user_id)

    search_text = _clean_text(search).lower()
    if search_text:
        projects = [
            project
            for project in projects
            if search_text in _clean_text(project.get("titulo")).lower()
            or search_text in _clean_text(project.get("descripcion")).lower()
        ]

    limited = projects[: _bounded_limit(limit)]
    return _ok(
        user_id=user_id,
        count=len(projects),
        returned=len(limited),
        projects=[_public_doc(project, PROJECT_FIELDS) for project in limited],
    )


def get_user_snapshot() -> dict:
    """Return a compact sensory snapshot for the active user."""
    return _ok(snapshot=build_user_snapshot(usuario_id=str(get_app_user_id())))


def get_dashboard_briefing(limit: int = 8) -> dict:
    """Return assistant-generated dashboard cards and work items."""
    return _ok(
        briefing=build_dashboard_briefing(
            usuario_id=str(get_app_user_id()),
            limit=limit,
        )
    )


def should_start_weekly_planning() -> dict:
    """Return whether the assistant should propose a weekly planning meeting."""
    return _ok(planning=assess_weekly_planning_need(usuario_id=str(get_app_user_id())))


def start_weekly_planning_session() -> dict:
    """Create or resume this week's planning session for the active user."""
    return _ok(planning=create_weekly_planning_session(usuario_id=str(get_app_user_id())))


def answer_weekly_planning_question(session_id: str, field: str, value: Any) -> dict:
    """Persist one answer in a weekly planning session."""
    try:
        result = save_weekly_planning_answer(
            session_id=session_id,
            field=_clean_text(field),
            value=value,
            usuario_id=str(get_app_user_id()),
        )
    except ValueError as exc:
        return _error(str(exc), code="planning_validation_error")
    return _ok(planning=result)


def build_weekly_plan(session_id: str | None = None) -> dict:
    """Build and store a deterministic weekly plan from the planning session."""
    try:
        result = build_plan_for_week(
            session_id=_clean_text(session_id) or None,
            usuario_id=str(get_app_user_id()),
        )
    except ValueError as exc:
        return _error(str(exc), code="planning_session_error")
    return _ok(planning=result)


def get_current_week_plan() -> dict:
    """Return the active user's current week planning session and plan."""
    return _ok(planning=fetch_current_week_plan(usuario_id=str(get_app_user_id())))


def get_project_context(project_id: str) -> dict:
    """Return project-centered context for the active user."""
    try:
        _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")

    context = build_project_context(project_id, usuario_id=str(get_app_user_id()))
    if context is None:
        return _error(
            "Proyecto no encontrado para el usuario activo.",
            code="project_not_found",
            project_id=project_id,
        )
    return _ok(context=context)


def list_heuristics(categories: list[str] | str | None = None) -> dict:
    """List registered deterministic heuristics."""
    return _ok(heuristics=list_registered_heuristics(categories=categories))


def explain_heuristic(name: str) -> dict:
    """Describe one registered deterministic heuristic."""
    heuristic = describe_heuristic(_clean_text(name))
    if heuristic is None:
        return _error("Heuristica no encontrada.", code="heuristic_not_found", name=name)
    return _ok(heuristic=heuristic)


def find_atomic_findings(
    categories: list[str] | str | None = None,
    limit: int = 100,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Run atomic deterministic heuristics without mutating data."""
    return _ok(
        analysis=detect_atomic_findings(
            usuario_id=str(get_app_user_id()),
            categories=categories,
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def find_bottlenecks(
    categories: list[str] | str | None = None,
    limit: int = 100,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Detect structural bottlenecks without mutating data."""
    return _ok(
        analysis=detect_bottlenecks(
            usuario_id=str(get_app_user_id()),
            categories=categories,
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def suggest_next_actions(
    limit: int = 10,
    categories: list[str] | str | None = None,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Suggest action payloads based on detected bottlenecks without executing them."""
    return _ok(
        suggestions=build_next_actions(
            usuario_id=str(get_app_user_id()),
            limit=limit,
            categories=categories,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def find_emergent_insights(
    limit: int = 20,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Build explainable emergent insights from atomic findings and dataset aggregates."""
    return _ok(
        insights=detect_emergent_insights(
            usuario_id=str(get_app_user_id()),
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def analyze_operating_system(
    limit: int = 20,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Return snapshot, atomic findings, emergent insights and prioritized recommendations."""
    return _ok(
        analysis=build_operating_system_analysis(
            usuario_id=str(get_app_user_id()),
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def get_operating_profile(
    limit: int = 10,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Return a scored operating profile for agent decision making."""
    return _ok(
        profile=build_operating_profile(
            usuario_id=str(get_app_user_id()),
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )
    )


def get_operating_map(limit: int = 50, include_events: bool = True) -> dict:
    """Return a read-only relationship map across the active user's system."""
    return _ok(
        operating_map=build_operating_map(
            usuario_id=str(get_app_user_id()),
            limit=limit,
            include_events=include_events,
        )
    )


def build_agent_context(
    limit: int = 10,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    """Prepare a compact context package for an external agent."""
    user_id = str(get_app_user_id())
    context = build_context_for_agent(
        usuario_id=user_id,
        limit=limit,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    context["operating_profile"] = build_operating_profile(
        usuario_id=user_id,
        limit=limit,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    context["operating_map"] = build_operating_map(
        usuario_id=user_id,
        limit=limit,
        include_events=True,
    )
    return _ok(context=context)


def health_check() -> dict:
    """Return MCP/runtime health without exposing secrets."""
    user_id = str(get_app_user_id())
    local_db = get_local_database()
    remote_db = get_remote_database()
    return _ok(
        user_id=user_id,
        checks={
            "local_database": local_db is not None,
            "remote_database": remote_db is not None,
            "mcp_handlers": True,
        },
    )


def create_project(
    titulo: str,
    descripcion: str | None = None,
    estado: str | None = "Activo",
    prioridad: str | None = "Media",
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict:
    """Create a project for the active user."""
    user_id = str(get_app_user_id())
    title = _clean_text(titulo)
    if not title:
        return _error("El campo 'titulo' es obligatorio.", field="titulo")

    project_data = {
        "usuario_id": user_id,
        "titulo": title,
        "descripcion": _clean_text(descripcion),
        "estado": _clean_text(estado) or "Activo",
        "prioridad": _clean_text(prioridad) or "Media",
    }
    if fecha_inicio:
        project_data["fecha_inicio"] = _clean_text(fecha_inicio)
    if fecha_fin:
        project_data["fecha_fin"] = _clean_text(fecha_fin)

    project = _capture_model_stdout(ProjectModel.insert_project, project_data, usuario_id=user_id)
    return _ok(user_id=user_id, project=_public_doc(project, PROJECT_FIELDS))


def update_project(
    project_id: str,
    titulo: str | None = None,
    descripcion: str | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
    progreso: int | str | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict:
    """Update safe project fields for the active user."""
    user_id = str(get_app_user_id())
    try:
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if project_oid is None:
        return _error("project_id es obligatorio.", code="invalid_object_id", field="project_id")
    project = ProjectModel.get_project_by_id(project_oid, usuario_id=user_id)
    if not project:
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")

    updates = {}
    for key, value in {
        "titulo": titulo,
        "descripcion": descripcion,
        "estado": estado,
        "prioridad": prioridad,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }.items():
        if value is not None:
            updates[key] = _clean_text(value)
    if progreso is not None:
        try:
            updates["progreso"] = max(0, min(int(progreso), 100))
        except (TypeError, ValueError):
            return _error("progreso debe ser un entero entre 0 y 100.", field="progreso")
    if not updates:
        return _error("No hay campos para actualizar.", code="empty_update")

    updated = _capture_model_stdout(ProjectModel.update_project, project_oid, updates, user_id)
    return _ok(user_id=user_id, project=_public_doc(updated, PROJECT_FIELDS))


def create_goal(
    titulo: str,
    project_id: str | None = None,
    descripcion: str | None = None,
    estado: str | None = "Activo",
    prioridad: str | None = "Media",
    progreso: int | str | None = 0,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict:
    """Create a goal for the active user, optionally linked to a project."""
    user_id = str(get_app_user_id())
    title = _clean_text(titulo)
    if not title:
        return _error("El campo 'titulo' es obligatorio.", field="titulo")
    try:
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if project_oid is not None and not ProjectModel.get_project_by_id(
        project_oid, usuario_id=user_id
    ):
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")
    try:
        parsed_progress = max(0, min(int(progreso or 0), 100))
    except (TypeError, ValueError):
        return _error("progreso debe ser un entero entre 0 y 100.", field="progreso")

    goal_data = {
        "usuario_id": user_id,
        "titulo": title,
        "descripcion": _clean_text(descripcion),
        "estado": _clean_text(estado) or "Activo",
        "prioridad": _clean_text(prioridad) or "Media",
        "progreso": parsed_progress,
    }
    if project_oid is not None:
        goal_data["project_id"] = project_oid
    if fecha_inicio:
        goal_data["fecha_inicio"] = _clean_text(fecha_inicio)
    if fecha_fin:
        goal_data["fecha_fin"] = _clean_text(fecha_fin)

    goal = _capture_model_stdout(GoalModel.insert_goal, goal_data, usuario_id=user_id)
    return _ok(user_id=user_id, goal=_public_doc(goal, GOAL_FIELDS))


def update_goal(
    goal_id: str,
    titulo: str | None = None,
    project_id: str | None = None,
    descripcion: str | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
    progreso: int | str | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> dict:
    """Update safe goal fields for the active user."""
    user_id = str(get_app_user_id())
    try:
        goal_oid = _parse_object_id(goal_id, "goal_id")
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if goal_oid is None:
        return _error("goal_id es obligatorio.", code="invalid_object_id", field="goal_id")
    goal = GoalModel.get_goal_by_id(goal_oid, usuario_id=user_id)
    if not goal:
        return _error("Objetivo no encontrado para el usuario activo.", code="goal_not_found")
    if project_oid is not None and not ProjectModel.get_project_by_id(
        project_oid, usuario_id=user_id
    ):
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")

    updates = {}
    for key, value in {
        "titulo": titulo,
        "descripcion": descripcion,
        "estado": estado,
        "prioridad": prioridad,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }.items():
        if value is not None:
            updates[key] = _clean_text(value)
    if project_oid is not None:
        updates["project_id"] = project_oid
    if progreso is not None:
        try:
            updates["progreso"] = max(0, min(int(progreso), 100))
        except (TypeError, ValueError):
            return _error("progreso debe ser un entero entre 0 y 100.", field="progreso")
    if not updates:
        return _error("No hay campos para actualizar.", code="empty_update")

    updated = _capture_model_stdout(GoalModel.update_goal, goal_oid, updates, user_id)
    return _ok(user_id=user_id, goal=_public_doc(updated, GOAL_FIELDS))


def create_task(
    contenido: str,
    goal_id: str | None = None,
    project_id: str | None = None,
    descripcion: str | None = None,
    fecha_limite: str | None = None,
    estado: str | None = "pendiente",
    prioridad: str | None = "media",
) -> dict:
    """Create a task for the active user, optionally linked to a goal/project."""
    user_id = str(get_app_user_id())
    content = _clean_text(contenido)
    if not content:
        return _error("El campo 'contenido' es obligatorio.", field="contenido")

    try:
        goal_oid = _parse_object_id(goal_id, "goal_id")
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")

    goal = None
    if goal_oid is not None:
        goal = GoalModel.get_goal_by_id(goal_oid, usuario_id=user_id)
        if not goal:
            return _error(
                "Objetivo no encontrado para el usuario activo.",
                code="goal_not_found",
                goal_id=str(goal_oid),
            )
        if project_oid is None and goal.get("project_id"):
            project_value = goal.get("project_id")
            if isinstance(project_value, ObjectId):
                project_oid = project_value

    if project_oid is not None:
        project = ProjectModel.get_project_by_id(project_oid, usuario_id=user_id)
        if not project:
            return _error(
                "Proyecto no encontrado para el usuario activo.",
                code="project_not_found",
                project_id=str(project_oid),
            )

    task_data = {
        "usuario_id": user_id,
        "contenido": content,
        "descripcion": _clean_text(descripcion),
        "estado": _clean_text(estado) or "pendiente",
        "prioridad": _clean_text(prioridad) or "media",
        "alarma_id": None,
    }
    if fecha_limite:
        task_data["fecha_limite"] = _clean_text(fecha_limite)
    if goal_oid is not None:
        task_data["objetivo_id"] = goal_oid
    if project_oid is not None:
        task_data["project_id"] = project_oid

    task = _capture_model_stdout(TaskModel.insert_task, task_data, usuario_id=user_id)
    return _ok(user_id=user_id, task=_public_doc(task, TASK_FIELDS))


def update_task(
    task_id: str,
    contenido: str | None = None,
    goal_id: str | None = None,
    project_id: str | None = None,
    descripcion: str | None = None,
    fecha_limite: str | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
) -> dict:
    """Update safe task fields for the active user."""
    user_id = str(get_app_user_id())
    try:
        task_oid = _parse_object_id(task_id, "task_id")
        goal_oid = _parse_object_id(goal_id, "goal_id")
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if task_oid is None:
        return _error("task_id es obligatorio.", code="invalid_object_id", field="task_id")

    task = TaskModel.get_task_by_id(task_oid, usuario_id=user_id)
    if not task:
        return _error("Tarea no encontrada para el usuario activo.", code="task_not_found")
    if goal_oid is not None:
        goal = GoalModel.get_goal_by_id(goal_oid, usuario_id=user_id)
        if not goal:
            return _error("Objetivo no encontrado para el usuario activo.", code="goal_not_found")
        if project_oid is None and goal.get("project_id"):
            project_value = goal.get("project_id")
            if isinstance(project_value, ObjectId):
                project_oid = project_value
    if project_oid is not None and not ProjectModel.get_project_by_id(
        project_oid, usuario_id=user_id
    ):
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")

    updates = {}
    for key, value in {
        "contenido": contenido,
        "descripcion": descripcion,
        "fecha_limite": fecha_limite,
        "estado": estado,
        "prioridad": prioridad,
    }.items():
        if value is not None:
            updates[key] = _clean_text(value)
    if goal_oid is not None:
        updates["objetivo_id"] = goal_oid
    if project_oid is not None:
        updates["project_id"] = project_oid
    if not updates:
        return _error("No hay campos para actualizar.", code="empty_update")

    updated = _capture_model_stdout(TaskModel.update_task, task_oid, updates, user_id)
    return _ok(user_id=user_id, task=_public_doc(updated, TASK_FIELDS))


def add_project_note(project_id: str, text: str) -> dict:
    """Append a Notion-like note to a project for the active user."""
    user_id = str(get_app_user_id())
    note_text = _clean_text(text)
    if not note_text:
        return _error("El campo 'text' es obligatorio.", field="text")
    try:
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if project_oid is None:
        return _error("project_id es obligatorio.", code="invalid_object_id", field="project_id")
    project = ProjectModel.get_project_by_id(project_oid, usuario_id=user_id)
    if not project:
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")
    note = {"_id": uuid4().hex, "text": note_text, "created_at": datetime.utcnow()}
    notes = list(project.get("notas", []) or [])
    notes.append(note)
    updated = _capture_model_stdout(
        ProjectModel.update_project, project_oid, {"notas": notes}, user_id
    )
    return _ok(user_id=user_id, note=_serialize(note), project=_public_doc(updated, PROJECT_FIELDS))


def list_project_documents(project_id: str, limit: int | str | None = 50) -> dict:
    """List project documents for the active user."""
    user_id = str(get_app_user_id())
    try:
        project_oid = _parse_object_id(project_id, "project_id")
    except ValueError as exc:
        return _error(str(exc), code="invalid_object_id")
    if project_oid is None:
        return _error("project_id es obligatorio.", code="invalid_object_id", field="project_id")
    if not ProjectModel.get_project_by_id(project_oid, usuario_id=user_id):
        return _error("Proyecto no encontrado para el usuario activo.", code="project_not_found")
    documents = ProjectDocumentModel.get_by_project(project_oid, usuario_id=user_id)
    bounded = _bounded_limit(limit)
    return _ok(
        user_id=user_id,
        count=len(documents),
        returned=min(len(documents), bounded),
        documents=[_public_doc(document, DOCUMENT_FIELDS) for document in documents[:bounded]],
    )


def sync_now() -> dict:
    """Run local/Atlas synchronization without exposing connection secrets."""
    if not ensure_remote_connection():
        return _error(
            "No hay conexion con la base de datos remota.",
            code="remote_unavailable",
        )
    user_id = str(get_app_user_id())
    try:
        deleted = flush_deletion_queue()
        promoted = ProjectDocumentModel.promote_pending_remote_uploads(usuario_id=user_id)
        pulled = sync_all_collections()
        pushed = sync_local_to_remote()
    except Exception as exc:
        return _error(str(exc), code="sync_failed")
    return _ok(
        user_id=user_id,
        sync={
            "deleted_remote": deleted,
            "promoted_documents": promoted,
            "pulled_documents": pulled,
            "pushed_documents": pushed,
        },
    )
