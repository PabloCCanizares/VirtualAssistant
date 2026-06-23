from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CascadeDeleteResult:
    deleted: bool = False
    errors: list[str] = field(default_factory=list)


def _default_dependencies():
    from model.goal_model import GoalModel
    from model.project_document_model import ProjectDocumentModel
    from model.project_model import ProjectModel
    from model.task_model import TaskModel
    from services.mongo_sync_service import queue_deletion

    return {
        "goal_model": GoalModel,
        "project_document_model": ProjectDocumentModel,
        "project_model": ProjectModel,
        "task_model": TaskModel,
        "queue_delete": queue_deletion,
    }


def delete_goal_cascade(
    goal_id: Any,
    *,
    usuario_id: Any,
    goal_model=None,
    task_model=None,
    queue_delete: Callable[[str, Any], Any] | None = None,
) -> CascadeDeleteResult:
    deps = _default_dependencies()
    goal_model = goal_model or deps["goal_model"]
    task_model = task_model or deps["task_model"]
    queue_delete = queue_delete or deps["queue_delete"]

    result = CascadeDeleteResult()
    task_ids = []

    try:
        tasks = task_model.get_tasks_by_goal(goal_id, usuario_id=usuario_id)
        task_ids = [task.get("_id") for task in tasks if task.get("_id")]
    except Exception as exc:
        result.errors.append(f"tareas: {exc}")

    if task_ids:
        try:
            task_model.delete_tasks_by_ids(task_ids, usuario_id=usuario_id)
            result.deleted = True
        except Exception as exc:
            result.errors.append(f"borrado tareas: {exc}")
        for task_id in task_ids:
            queue_delete("Tasks", task_id)

    try:
        deleted_goal = goal_model.delete_goal(goal_id, usuario_id=usuario_id)
        result.deleted = result.deleted or bool(deleted_goal)
        if deleted_goal:
            queue_delete("Goals", goal_id)
    except Exception as exc:
        result.errors.append(f"borrado objetivo: {exc}")

    return result


def delete_project_cascade(
    project_id: Any,
    *,
    usuario_id: Any,
    goal_model=None,
    project_document_model=None,
    project_model=None,
    task_model=None,
    queue_delete: Callable[[str, Any], Any] | None = None,
) -> CascadeDeleteResult:
    deps = _default_dependencies()
    goal_model = goal_model or deps["goal_model"]
    project_document_model = project_document_model or deps["project_document_model"]
    project_model = project_model or deps["project_model"]
    task_model = task_model or deps["task_model"]
    queue_delete = queue_delete or deps["queue_delete"]

    result = CascadeDeleteResult()

    goals = []
    goal_ids = []
    task_ids = []
    try:
        goals = goal_model.get_by_project(project_id, usuario_id=usuario_id)
        goal_ids = [goal.get("_id") for goal in goals if goal.get("_id")]
    except Exception as exc:
        result.errors.append(f"objetivos: {exc}")

    for goal_id in goal_ids:
        try:
            tasks = task_model.get_tasks_by_goal(goal_id, usuario_id=usuario_id)
            task_ids.extend([task.get("_id") for task in tasks if task.get("_id")])
        except Exception as exc:
            result.errors.append(f"tareas: {exc}")

    if task_ids:
        try:
            task_model.delete_tasks_by_ids(task_ids, usuario_id=usuario_id)
            result.deleted = True
        except Exception as exc:
            result.errors.append(f"borrado tareas: {exc}")
        for task_id in task_ids:
            queue_delete("Tasks", task_id)

    if goal_ids:
        try:
            goal_model.delete_goals_by_ids(goal_ids, usuario_id=usuario_id)
            result.deleted = True
        except Exception as exc:
            result.errors.append(f"borrado objetivos: {exc}")
        for goal_id in goal_ids:
            queue_delete("Goals", goal_id)

    try:
        docs = project_document_model.get_by_project(project_id, usuario_id=usuario_id)
    except Exception as exc:
        docs = []
        result.errors.append(f"documentos: {exc}")

    for doc in docs:
        try:
            deleted_doc = project_document_model.delete_document(doc["_id"], usuario_id=usuario_id)
            result.deleted = result.deleted or bool(deleted_doc)
        except Exception as exc:
            result.errors.append(f"borrado documento: {exc}")
        queue_delete("ProjectDocuments", doc.get("_id"))

    try:
        deleted_project = project_model.delete_project(project_id, usuario_id=usuario_id)
        result.deleted = result.deleted or bool(deleted_project)
    except Exception as exc:
        result.errors.append(f"borrado proyecto: {exc}")
    queue_delete("Projects", project_id)

    return result
