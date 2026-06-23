import json
import logging
from typing import Any, Dict, Optional, Tuple

from bson import ObjectId

from ai.services.action_state import clear_pending_action
from ai.services.session_mutations_state import append_session_mutation
from ai.state import AppState
from database.mongo_conn import flush_deletion_queue, get_app_user_id, queue_deletion
from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from services.event_service import normalize_reference
from services.project_service import (
    delete_goal_cascade as service_delete_goal_cascade,
)
from services.project_service import (
    delete_project_cascade as service_delete_project_cascade,
)

logger = logging.getLogger(__name__)

CONFIRM_REQUIRED_ACTIONS = {"delete_project", "delete_goal", "delete_task", "delete_event"}


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
    title = params.get("titulo")
    project, matches = _match_by_title(context.get("projects", []), "titulo", title)
    if project:
        return str(project.get("_id")), None
    if matches:
        return None, "He encontrado varios proyectos con ese nombre. ¿Cual exactamente?"
    return None, "¿Que proyecto quieres usar? Indica el nombre."


def _resolve_goal_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    gid = params.get("goal_id")
    if gid:
        return str(gid), None
    title = params.get("titulo")
    goal, matches = _match_by_title(context.get("goals", []), "titulo", title)
    if goal:
        return str(goal.get("_id")), None
    if matches:
        return None, "He encontrado varios objetivos con ese nombre. ¿Cual exactamente?"
    return None, "¿Que objetivo quieres usar? Indica el nombre."


def _resolve_task_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    tid = params.get("task_id")
    if tid:
        return str(tid), None
    title = params.get("contenido")
    task, matches = _match_by_title(context.get("tasks", []), "contenido", title)
    if task:
        return str(task.get("_id")), None
    if matches:
        return None, "He encontrado varias tareas con ese texto. ¿Cual exactamente?"
    return None, "¿Que tarea quieres usar? Indica el texto exacto."


def _resolve_event_id(params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    eid = params.get("event_id")
    if eid:
        return str(eid), None
    title = params.get("titulo")
    event, matches = _match_by_title(context.get("events", []), "titulo", title)
    if event:
        return str(event.get("_id")), None
    if matches:
        return None, "He encontrado varios eventos con ese nombre. ¿Cual exactamente?"
    return None, "¿Que evento quieres usar? Indica el nombre."


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
    result = service_delete_project_cascade(
        project_id,
        usuario_id=user_id,
        queue_delete=queue_deletion,
    )
    if result.errors:
        logger.warning("delete_project_cascade completed with warnings: %s", result.errors)


def _delete_goal_cascade(goal_id: str, user_id: str) -> None:
    result = service_delete_goal_cascade(
        goal_id,
        usuario_id=user_id,
        queue_delete=queue_deletion,
    )
    if result.errors:
        logger.warning("delete_goal_cascade completed with warnings: %s", result.errors)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _build_update_fields(params: Dict[str, Any], allowed_keys: set) -> Dict[str, Any]:
    """Extrae solo los campos permitidos del dict de parametros para un update."""
    updates = {}
    for key in allowed_keys:
        if key in params and params[key] is not None:
            updates[key] = params[key]
    return updates


def _result(message: str, result_id: Optional[str] = None) -> Dict[str, Any]:
    """Construye el dict de retorno unificado con campos para modo cola y modo simple."""
    return {
        "final_response": message,
        "action_result_message": message,
        "action_result_id": result_id,
    }


def action_executor_node(state: AppState, _llm) -> AppState:
    user_id = _ensure_user_id(state)

    pending = state.get("pending_action_intent") or {}
    action_name = pending.get("action_name") or state.get("action_name")
    parameters = pending.get("parameters") or state.get("action_parameters") or {}

    if action_name in CONFIRM_REQUIRED_ACTIONS and not state.get("action_confirmed", False):
        msg = (
            "Esta accion requiere confirmacion explicita. "
            "Responde 'confirmo' para continuar o 'cancela' para abortar."
        )
        return {
            "final_response": msg,
            "action_result_message": msg,
            "action_result_id": None,
            "pending_action_intent": pending or {"action_name": action_name, "parameters": parameters},
        }

    context = _load_context(state)

    if not action_name:
        return _result("No se detecto ninguna accion para ejecutar.")

    try:
        # ── CREATE ─────────────────────────────────────────────────
        if action_name == "create_project":
            titulo = parameters.get("titulo") or parameters.get("title")
            if not titulo:
                return _result("Necesito el titulo del proyecto para crearlo.")
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
            new_id = str(data.get("_id", ""))
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "created", "type": "project", "id": new_id, "name": titulo})
            return _result(f"Proyecto creado: {titulo}.", new_id)

        if action_name == "create_goal":
            titulo = parameters.get("titulo") or parameters.get("title")
            if not titulo:
                return _result("Necesito el titulo del objetivo para crearlo.")
            project_id, clar = _resolve_project_id(parameters, context)
            if clar:
                return _result(clar)
            data = {
                "titulo": titulo,
                "descripcion": parameters.get("descripcion"),
                "project_id": project_id,
                "fecha_inicio": parameters.get("fecha_inicio"),
                "fecha_fin": parameters.get("fecha_fin"),
                "prioridad": parameters.get("prioridad") or "Media",
                "estado": parameters.get("estado") or "En progreso",
                "progreso": _safe_int(parameters.get("progreso"), 0),
                "usuario_id": user_id,
            }
            GoalModel.insert_goal(data)
            new_id = str(data.get("_id", ""))
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "created", "type": "goal", "id": new_id, "name": titulo})
            return _result(f"Objetivo creado: {titulo}.", new_id)

        if action_name == "create_task":
            contenido = parameters.get("contenido") or parameters.get("titulo")
            if not contenido:
                return _result("Necesito el contenido de la tarea para crearla.")
            goal_id, clar = _resolve_goal_id(parameters, context)
            if clar:
                return _result(clar)
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
            new_id = str(data.get("_id", ""))
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "created", "type": "task", "id": new_id, "name": contenido})
            return _result(f"Tarea creada: {contenido}.", new_id)

        if action_name == "create_event":
            titulo = parameters.get("titulo")
            if not titulo:
                return _result("Necesito el titulo del evento para crearlo.")
            fecha_inicio = parameters.get("fecha_inicio")
            if not fecha_inicio:
                return _result("Necesito la fecha de inicio del evento.")
            data = {
                "titulo": titulo,
                "descripcion": parameters.get("descripcion"),
                "fecha_inicio": fecha_inicio,
                "fecha_fin": parameters.get("fecha_fin"),
                "tipo_evento": parameters.get("tipo_evento"),
                "usuario_id": user_id,
            }
            ref_id, ref_tipo = normalize_reference(
                parameters.get("referencia_id"),
                parameters.get("referencia_tipo"),
                id_tarea=parameters.get("id_tarea"),
                id_objetivo=parameters.get("id_objetivo"),
            )
            if ref_id and ref_tipo:
                data["referencia_id"] = ref_id
                data["referencia_tipo"] = ref_tipo
            new_id = str(eventModel.insert_event(data, usuario_id=user_id) or "")
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "created", "type": "event", "id": new_id, "name": titulo})
            return _result(f"Evento creado: {titulo}.", new_id)

        # ── UPDATE ─────────────────────────────────────────────────
        if action_name == "update_project":
            project_id, clar = _resolve_project_id(parameters, context)
            if clar:
                return _result(clar)
            allowed = {"titulo", "descripcion", "estado", "prioridad", "fecha_inicio", "fecha_fin"}
            updates = _build_update_fields(parameters, allowed)
            if not updates:
                return _result("No se indicaron campos para actualizar en el proyecto.")
            ProjectModel.update_project(project_id, updates, usuario_id=user_id)
            clear_pending_action(user_id)
            nombre = parameters.get("titulo")
            append_session_mutation(user_id, {"action": "updated", "type": "project", "id": project_id, "name": nombre})
            campos = ", ".join(updates.keys())
            return _result(f"Proyecto actualizado ({campos}).", project_id)

        if action_name == "update_goal":
            goal_id, clar = _resolve_goal_id(parameters, context)
            if clar:
                return _result(clar)
            allowed = {"titulo", "descripcion", "estado", "prioridad", "fecha_inicio", "fecha_fin", "progreso"}
            updates = _build_update_fields(parameters, allowed)
            if not updates:
                return _result("No se indicaron campos para actualizar en el objetivo.")
            if "progreso" in updates:
                updates["progreso"] = _safe_int(updates["progreso"], 0)
            GoalModel.update_goal(goal_id, updates, usuario_id=user_id)
            clear_pending_action(user_id)
            nombre = parameters.get("titulo")
            append_session_mutation(user_id, {"action": "updated", "type": "goal", "id": goal_id, "name": nombre})
            campos = ", ".join(updates.keys())
            return _result(f"Objetivo actualizado ({campos}).", goal_id)

        if action_name == "update_task":
            task_id, clar = _resolve_task_id(parameters, context)
            if clar:
                return _result(clar)
            allowed = {"contenido", "descripcion", "fecha_limite", "estado", "prioridad"}
            updates = _build_update_fields(parameters, allowed)
            if not updates:
                return _result("No se indicaron campos para actualizar en la tarea.")
            TaskModel.update_task(task_id, updates, usuario_id=user_id)
            clear_pending_action(user_id)
            nombre = parameters.get("contenido")
            append_session_mutation(user_id, {"action": "updated", "type": "task", "id": task_id, "name": nombre})
            campos = ", ".join(updates.keys())
            return _result(f"Tarea actualizada ({campos}).", task_id)

        if action_name == "mark_task_complete":
            task_id, clar = _resolve_task_id(parameters, context)
            if clar:
                return _result(clar)
            TaskModel.update_task(task_id, {"estado": "completada"}, usuario_id=user_id)
            clear_pending_action(user_id)
            nombre = parameters.get("contenido")
            append_session_mutation(user_id, {"action": "updated", "type": "task", "id": task_id, "name": nombre})
            return _result("Tarea marcada como completada.", task_id)

        # ── DELETE ─────────────────────────────────────────────────
        if action_name == "delete_project":
            project_id, clar = _resolve_project_id(parameters, context)
            if clar:
                return _result(clar)
            nombre = parameters.get("titulo")
            _delete_project_cascade(project_id, user_id)
            try:
                flush_deletion_queue()
            except Exception:
                logger.warning("No se pudo vaciar DeleteQueue tras delete_project", exc_info=True)
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "deleted", "type": "project", "id": project_id, "name": nombre})
            return _result("Proyecto eliminado correctamente.", project_id)

        if action_name == "delete_goal":
            goal_id, clar = _resolve_goal_id(parameters, context)
            if clar:
                return _result(clar)
            nombre =parameters.get("titulo")
            _delete_goal_cascade(goal_id, user_id)
            try:
                flush_deletion_queue()
            except Exception:
                logger.warning("No se pudo vaciar DeleteQueue tras delete_goal", exc_info=True)
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "deleted", "type": "goal", "id": goal_id, "name": nombre})
            return _result("Objetivo eliminado correctamente.", goal_id)

        if action_name == "delete_task":
            task_id, clar = _resolve_task_id(parameters, context)
            if clar:
                return _result(clar)
            nombre = parameters.get("contenido")
            TaskModel.delete_task(task_id, usuario_id=user_id)
            queue_deletion("Tasks", task_id)
            try:
                flush_deletion_queue()
            except Exception:
                logger.warning("No se pudo vaciar DeleteQueue tras delete_task", exc_info=True)
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "deleted", "type": "task", "id": task_id, "name": nombre})
            return _result("Tarea eliminada correctamente.", task_id)

        if action_name == "delete_event":
            event_id, clar = _resolve_event_id(parameters, context)
            if clar:
                return _result(clar)
            nombre = parameters.get("titulo")
            eventModel.delete_event(event_id, usuario_id=user_id)
            queue_deletion("Events", event_id)
            try:
                flush_deletion_queue()
            except Exception:
                logger.warning("No se pudo vaciar DeleteQueue tras delete_event", exc_info=True)
            clear_pending_action(user_id)
            append_session_mutation(user_id, {"action": "deleted", "type": "event", "id": event_id, "name": nombre})
            return _result("Evento eliminado correctamente.", event_id)

        return _result("Accion no soportada en este momento.")

    except Exception as exc:
        logger.exception("action_executor_node: fallo al ejecutar accion '%s'", action_name)
        return _result(f"No pude ejecutar la accion: {exc}")
