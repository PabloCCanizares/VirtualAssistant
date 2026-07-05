"""Context-building services for GoalMind AI agents."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from bson import ObjectId

from database.mongo_conn import get_app_user_id
from model.daily_metric_model import DailyMetricModel
from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel

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

DAILY_METRIC_FIELDS = (
    "_id",
    "date",
    "sleep_hours",
    "sleep_source",
    "sleep_unit",
    "mood_score",
    "mood_label",
    "mood_source",
    "weather_code",
    "weather_label",
    "weather_kind",
    "weather_source",
    "weather_location_name",
    "weather_temp_mean_c",
    "weather_temp_max_c",
    "weather_temp_min_c",
    "weather_apparent_temp_mean_c",
    "weather_precipitation_mm",
    "weather_precipitation_hours",
    "weather_wind_speed_max_kmh",
    "weather_shortwave_radiation_mj_m2",
    "weather_cloud_cover_mean_pct",
    "weather_fetched_at",
    "created_at",
    "updated_at",
)


def serialize_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    return value


def public_doc(doc: dict | None, fields: tuple[str, ...]) -> dict | None:
    if not doc:
        return None
    return {field: serialize_value(doc[field]) for field in fields if field in doc}


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


def doc_id(doc: dict | None) -> str:
    if not doc or "_id" not in doc:
        return ""
    return str(doc["_id"])


def ref_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def is_completed(item: dict) -> bool:
    status = str(item.get("estado") or "").strip().lower()
    return status in {"completada", "completado", "done", "finalizada", "finalizado"}


def is_paused(item: dict) -> bool:
    status = str(item.get("estado") or "").strip().lower()
    return status in {
        "pausada",
        "pausado",
        "paused",
        "pause",
        "en pausa",
        "on hold",
        "hold",
        "suspendida",
        "suspendido",
    }


def is_archived(item: dict) -> bool:
    status = str(item.get("estado") or "").strip().lower()
    return status in {"archivado", "archivada", "archivo", "cerrado", "cerrada"}


def is_active_project(project: dict) -> bool:
    return not is_completed(project) and not is_paused(project) and not is_archived(project)


def is_active_goal(goal: dict) -> bool:
    return not is_completed(goal) and not is_paused(goal) and not is_archived(goal)


def item_timestamp(item: dict) -> datetime | None:
    for key in (
        "updated_at",
        "fecha_modificacion",
        "modified_at",
        "fecha_creacion",
        "created_at",
        "uploaded_at",
        "fecha_inicio",
    ):
        parsed = parse_datetime(item.get(key))
        if parsed is not None:
            return parsed
    return None


def get_user_dataset(usuario_id: str | None = None) -> dict:
    user_id = str(usuario_id or get_app_user_id())
    projects = ProjectModel.get_all_projects(usuario_id=user_id)
    goals = GoalModel.get_all_goals(usuario_id=user_id)
    tasks = TaskModel.get_all_tasks(usuario_id=user_id)
    documents = ProjectDocumentModel.get_all_documents(usuario_id=user_id)
    events = eventModel.get_all_events(usuario_id=user_id)
    daily_metrics = DailyMetricModel.get_recent(limit=30, usuario_id=user_id)
    return {
        "user_id": user_id,
        "projects": projects,
        "goals": goals,
        "tasks": tasks,
        "documents": documents,
        "events": events,
        "daily_metrics": daily_metrics,
    }


def _goal_project_id(goal: dict) -> str:
    return ref_id(goal.get("project_id"))


def _task_goal_id(task: dict) -> str:
    return ref_id(task.get("objetivo_id") or task.get("goal_id"))


def _task_project_id(task: dict) -> str:
    return ref_id(task.get("project_id"))


def _task_due_at(task: dict) -> datetime | None:
    return parse_datetime(task.get("fecha_limite"))


def build_active_scope(dataset: dict) -> dict[str, Any]:
    """Return only entities that should contribute to operational cognition."""
    project_by_id = {doc_id(project): project for project in dataset["projects"]}
    active_projects = [project for project in dataset["projects"] if is_active_project(project)]
    active_project_ids = {doc_id(project) for project in active_projects}

    def project_scope_allows(project_id: str) -> bool:
        return not project_id or project_id not in project_by_id or project_id in active_project_ids

    active_goals = [
        goal
        for goal in dataset["goals"]
        if is_active_goal(goal) and project_scope_allows(_goal_project_id(goal))
    ]
    goal_by_id = {doc_id(goal): goal for goal in dataset["goals"]}
    active_goal_ids = {doc_id(goal) for goal in active_goals}

    def goal_scope_allows(goal_id: str) -> bool:
        return not goal_id or goal_id not in goal_by_id or goal_id in active_goal_ids

    active_tasks = [
        task
        for task in dataset["tasks"]
        if project_scope_allows(_task_project_id(task)) and goal_scope_allows(_task_goal_id(task))
    ]
    active_documents = [
        document
        for document in dataset["documents"]
        if project_scope_allows(ref_id(document.get("project_id")))
        and goal_scope_allows(ref_id(document.get("goal_id")))
    ]

    return {
        "projects": active_projects,
        "goals": active_goals,
        "tasks": active_tasks,
        "documents": active_documents,
        "project_ids": active_project_ids,
        "goal_ids": active_goal_ids,
        "ignored_projects": [
            project for project in dataset["projects"] if doc_id(project) not in active_project_ids
        ],
        "ignored_goals": [
            goal for goal in dataset["goals"] if doc_id(goal) not in active_goal_ids
        ],
    }


def _recent_items(dataset: dict, *, limit: int = 10) -> list[dict]:
    typed_items: list[dict] = []
    specs = (
        ("project", dataset["projects"], "titulo", PROJECT_FIELDS),
        ("goal", dataset["goals"], "titulo", GOAL_FIELDS),
        ("task", dataset["tasks"], "contenido", TASK_FIELDS),
        ("document", dataset["documents"], "original_name", DOCUMENT_FIELDS),
    )
    for item_type, items, label_field, fields in specs:
        for item in items:
            timestamp = item_timestamp(item)
            if timestamp is None:
                continue
            typed_items.append(
                {
                    "type": item_type,
                    "id": doc_id(item),
                    "title": str(item.get(label_field) or item.get("filename") or ""),
                    "timestamp": timestamp,
                    "item": public_doc(item, fields),
                }
            )
    typed_items.sort(key=lambda item: item["timestamp"], reverse=True)
    return [
        {**item, "timestamp": serialize_value(item["timestamp"])} for item in typed_items[:limit]
    ]


def get_user_snapshot(usuario_id: str | None = None, *, now: datetime | None = None) -> dict:
    current = now or datetime.utcnow()
    dataset = get_user_dataset(usuario_id=usuario_id)
    active_scope = build_active_scope(dataset)
    active_dataset = {
        **dataset,
        "projects": active_scope["projects"],
        "goals": active_scope["goals"],
        "tasks": active_scope["tasks"],
        "documents": active_scope["documents"],
    }

    project_ids_with_goals = {_goal_project_id(goal) for goal in active_scope["goals"]}
    goal_ids_with_tasks = {
        _task_goal_id(task) for task in active_scope["tasks"] if _task_goal_id(task)
    }

    projects_without_goals = [
        project for project in active_scope["projects"] if doc_id(project) not in project_ids_with_goals
    ]
    goals_without_tasks = [
        goal for goal in active_scope["goals"] if doc_id(goal) not in goal_ids_with_tasks
    ]
    pending_tasks = [task for task in active_scope["tasks"] if not is_completed(task)]
    completed_tasks = [task for task in active_scope["tasks"] if is_completed(task)]

    upcoming = []
    for task in pending_tasks:
        due_at = _task_due_at(task)
        if due_at is not None and due_at >= current:
            upcoming.append(
                {
                    "task": public_doc(task, TASK_FIELDS),
                    "due_at": serialize_value(due_at),
                    "days_until_due": (due_at.date() - current.date()).days,
                }
            )
    upcoming.sort(key=lambda item: item["due_at"])

    return {
        "user_id": dataset["user_id"],
        "generated_at": serialize_value(current),
        "counts": {
            "projects": len(active_scope["projects"]),
            "goals": len(active_scope["goals"]),
            "tasks": len(active_scope["tasks"]),
            "documents": len(active_scope["documents"]),
            "events": len(dataset["events"]),
            "daily_metrics": len(dataset.get("daily_metrics", [])),
            "pending_tasks": len(pending_tasks),
            "completed_tasks": len(completed_tasks),
            "active_projects": len(active_scope["projects"]),
            "projects_without_goals": len(projects_without_goals),
            "goals_without_tasks": len(goals_without_tasks),
            "ignored_inactive_projects": len(active_scope["ignored_projects"]),
            "ignored_inactive_goals": len(active_scope["ignored_goals"]),
        },
        "projects_without_goals": [
            public_doc(project, PROJECT_FIELDS) for project in projects_without_goals
        ],
        "goals_without_tasks": [public_doc(goal, GOAL_FIELDS) for goal in goals_without_tasks],
        "upcoming_deadlines": upcoming[:10],
        "recent_daily_metrics": [
            public_doc(metric, DAILY_METRIC_FIELDS)
            for metric in dataset.get("daily_metrics", [])[:14]
        ],
        "recent_activity": _recent_items(active_dataset, limit=10),
    }


def get_project_context(project_id: str, usuario_id: str | None = None) -> dict | None:
    user_id = str(usuario_id or get_app_user_id())
    project = ProjectModel.get_project_by_id(project_id, usuario_id=user_id)
    if not project:
        return None

    goals = GoalModel.get_by_project(project["_id"], usuario_id=user_id)
    tasks = TaskModel.get_all_tasks(usuario_id=user_id)
    documents = ProjectDocumentModel.get_by_project(project["_id"], usuario_id=user_id)
    goal_ids = {doc_id(goal) for goal in goals}

    tasks_by_goal: dict[str, list[dict]] = {doc_id(goal): [] for goal in goals}
    project_unlinked_tasks: list[dict] = []
    for task in tasks:
        goal_id = _task_goal_id(task)
        if goal_id in tasks_by_goal:
            tasks_by_goal[goal_id].append(task)
            continue
        if ref_id(task.get("project_id")) == doc_id(project):
            project_unlinked_tasks.append(task)

    gaps = []
    if not goals:
        gaps.append(
            {
                "type": "project_without_goals",
                "severity": "high",
                "message": "El proyecto no tiene objetivos asociados.",
            }
        )
    for goal in goals:
        if not tasks_by_goal.get(doc_id(goal)):
            gaps.append(
                {
                    "type": "goal_without_tasks",
                    "severity": "medium",
                    "goal_id": doc_id(goal),
                    "message": "El objetivo no tiene tareas asociadas.",
                }
            )
    if project_unlinked_tasks:
        gaps.append(
            {
                "type": "project_tasks_without_goal",
                "severity": "medium",
                "count": len(project_unlinked_tasks),
                "message": "Hay tareas vinculadas al proyecto pero no a un objetivo.",
            }
        )
    if not documents:
        gaps.append(
            {
                "type": "project_without_documents",
                "severity": "low",
                "message": "El proyecto no tiene documentos asociados.",
            }
        )

    progress = ProjectModel.calculate_progress_from_goals(goals)
    return {
        "user_id": user_id,
        "project": public_doc(project, PROJECT_FIELDS),
        "progress": progress,
        "goals": [
            {
                "goal": public_doc(goal, GOAL_FIELDS),
                "tasks": [
                    public_doc(task, TASK_FIELDS) for task in tasks_by_goal.get(doc_id(goal), [])
                ],
            }
            for goal in goals
        ],
        "unlinked_project_tasks": [
            public_doc(task, TASK_FIELDS) for task in project_unlinked_tasks
        ],
        "documents": [public_doc(document, DOCUMENT_FIELDS) for document in documents],
        "notes": serialize_value(project.get("notas", []) or []),
        "gaps": gaps,
        "related_ids": {
            "goal_ids": sorted(goal_ids),
            "document_ids": [doc_id(document) for document in documents],
        },
    }
