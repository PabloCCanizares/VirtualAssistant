import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from bson import ObjectId

from database.mongo_conn import queue_deletion, flush_deletion_queue, get_app_user_id
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.action_state import clear_pending_action
from state import AppState


CONFIRM_REQUIRED_ACTIONS = {"delete_project", "delete_goal", "delete_task"}


def _load_context(state: AppState) -> Dict[str, Any]:
    raw = state.get("context_json") or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def _match_by_title(items, title_key: str, query: str) -> Tuple[Optional[Dict[str, Any]], list]:
    if not query:
        return None, []
    q = _normalize_text(query)
    matches = []
    for item in items or []:
        title = _normalize_text(str(item.get(title_key, "")))
        if not title:
            continue
        if q == title or q in title:
            matches.append(item)
    if len(matches) == 1:
        return matches[0], matches
    return None, matches


def _resolve_project_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    pid = params.get("project_id")
    if pid:
        return str(pid), None
    title = params.get("project_title") or params.get("titulo_proyecto") or params.get("proyecto")
    project, matches = _match_by_title(context.get("projects", []), "titulo", title)
    if project:
        return str(project.get("_id")), None
    if matches:
        return None, "He encontrado varios proyectos con ese nombre. ¿Cuál exactamente?"
    return None, "¿Qué proyecto quieres usar? Indica el nombre."


def _resolve_goal_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    gid = params.get("goal_id")
    if gid:
        return str(gid), None
    title = params.get("goal_title") or params.get("titulo_objetivo") or params.get("objetivo")
    goal, matches = _match_by_title(context.get("goals", []), "titulo", title)
    if goal:
        return str(goal.get("_id")), None
    if matches:
        return None, "He encontrado varios objetivos con ese nombre. ¿Cuál exactamente?"
    return None, "¿Qué objetivo quieres usar? Indica el nombre."


def _resolve_task_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    tid = params.get("task_id")
    if tid:
        return str(tid), None
    title = params.get("task_title") or params.get("contenido") or params.get("tarea")
    task, matches = _match_by_title(context.get("tasks", []), "contenido", title)
    if task:
        return str(task.get("_id")), None
    if matches:
        return None, "He encontrado varias tareas con ese texto. ¿Cuál exactamente?"
    return None, "¿Qué tarea quieres usar? Indica el texto exacto."


def _parse_object_id(value: Optional[str]) -> Optional[ObjectId]:
    if not value:
        return None
    try:
        if ObjectId.is_valid(str(value)):
            return ObjectId(str(value))
    except Exception:
        return None
    return None


def _ensure_user_id(state: AppState) -> str:
    return str(state.get("user_id") or get_app_user_id())


def _delete_project_cascade(project_id: str, user_id: str) -> None:
    goals = GoalModel.get_by_project(project_id, usuario_id=user_id)
    goal_ids = [g.get("_id") for g in goals if g.get("_id")]

    task_ids = []
    for gid in goal_ids:
        tasks = TaskModel.get_tasks_by_goal(gid, usuario_id=user_id)
        task_ids.extend([t.get("_id") for t in tasks if t.get("_id")])

    if task_ids:
        TaskModel.delete_tasks_by_ids(task_ids)
        for tid in task_ids:
            queue_deletion("Tasks", tid)

    if goal_ids:
        GoalModel.delete_goals_by_ids(goal_ids)
        for gid in goal_ids:
            queue_deletion("Goals", gid)

    docs = ProjectDocumentModel.get_by_project(project_id)
    for doc in docs:
        if not doc.get("upload_id"):
            local_path = doc.get("local_path")
            if local_path:
                try:
                    Path(local_path).unlink(missing_ok=True)
                except Exception:
                    pass
        try:
            ProjectDocumentModel.delete_document(doc.get("_id"))
        except Exception:
            pass
        queue_deletion("ProjectDocuments", doc.get("_id"))

    ProjectModel.delete_project(project_id)
    queue_deletion("Projects", project_id)


def _delete_goal_cascade(goal_id: str, user_id: str) -> None:
    tasks = TaskModel.get_tasks_by_goal(goal_id, usuario_id=user_id)
    task_ids = [t.get("_id") for t in tasks if t.get("_id")]
    if task_ids:
        TaskModel.delete_tasks_by_ids(task_ids)
        for tid in task_ids:
            queue_deletion("Tasks", tid)

    GoalModel.delete_goal(goal_id)
    queue_deletion("Goals", goal_id)


def action_executor_node(state: AppState, llm) -> AppState:
    user_id = _ensure_user_id(state)
    clear_pending_action(user_id)

    pending = state.get("pending_action_intent") or {}
    action_name = pending.get("action_name") or state.get("action_name")
    parameters = pending.get("parameters") or state.get("action_parameters") or {}

    context = _load_context(state)

    if not action_name:
        return {"final_response": "No se detecto ninguna accion para ejecutar."}

    try:
        if action_name == "create_project":
            titulo = parameters.get("titulo") or parameters.get("title")
            if not titulo:
                return {"final_response": "Necesito el titulo del proyecto para crearlo."}
            data = {
                "titulo": titulo,
                "descripcion": parameters.get("descripcion"),
                "estado": parameters.get("estado") or "Activo",
                "prioridad": parameters.get("prioridad") or "Media",
                "fecha_inicio": parameters.get("fecha_inicio"),
                "fecha_fin": parameters.get("fecha_fin"),
                "usuario_id": user_id,
            }
            ProjectModel.insert_project(data)
            return {"final_response": f"✅ Proyecto creado: {titulo}."}

        if action_name == "create_goal":
            titulo = parameters.get("titulo") or parameters.get("title")
            if not titulo:
                return {"final_response": "Necesito el titulo del objetivo para crearlo."}
            project_id, clar = _resolve_project_id(parameters, context)
            if clar:
                return {"final_response": clar}
            data = {
                "titulo": titulo,
                "descripcion": parameters.get("descripcion"),
                "project_id": project_id,
                "fecha_inicio": parameters.get("fecha_inicio"),
                "fecha_fin": parameters.get("fecha_fin"),
                "prioridad": parameters.get("prioridad") or "Media",
                "estado": parameters.get("estado") or "En progreso",
                "progreso": int(parameters.get("progreso") or 0),
                "usuario_id": user_id,
            }
            GoalModel.insert_goal(data)
            return {"final_response": f"✅ Objetivo creado: {titulo}."}

        if action_name == "create_task":
            contenido = parameters.get("contenido") or parameters.get("titulo")
            if not contenido:
                return {"final_response": "Necesito el contenido de la tarea para crearla."}
            goal_id, clar = _resolve_goal_id(parameters, context)
            if clar:
                return {"final_response": clar}
            objetivo_oid = _parse_object_id(goal_id)
            data = {
                "usuario_id": user_id,
                "contenido": contenido,
                "descripcion": parameters.get("descripcion"),
                "fecha_limite": parameters.get("fecha_limite"),
                "estado": parameters.get("estado") or "pendiente",
                "prioridad": parameters.get("prioridad") or "media",
                "objetivo_id": objetivo_oid or goal_id,
                "alarma_id": None,
            }
            TaskModel.insert_task(data)
            return {"final_response": f"✅ Tarea creada: {contenido}."}

        if action_name == "delete_project":
            project_id, clar = _resolve_project_id(parameters, context)
            if clar:
                return {"final_response": clar}
            _delete_project_cascade(project_id, user_id)
            flush_deletion_queue()
            return {"final_response": "🗑️ Proyecto eliminado correctamente."}

        if action_name == "delete_goal":
            goal_id, clar = _resolve_goal_id(parameters, context)
            if clar:
                return {"final_response": clar}
            _delete_goal_cascade(goal_id, user_id)
            flush_deletion_queue()
            return {"final_response": "🗑️ Objetivo eliminado correctamente."}

        if action_name == "delete_task":
            task_id, clar = _resolve_task_id(parameters, context)
            if clar:
                return {"final_response": clar}
            TaskModel.delete_task(task_id, usuario_id=user_id)
            queue_deletion("Tasks", task_id)
            flush_deletion_queue()
            return {"final_response": "🗑️ Tarea eliminada correctamente."}

        return {"final_response": "Accion no soportada en este momento."}

    except Exception as exc:
        return {"final_response": f"No pude ejecutar la accion: {exc}"}
