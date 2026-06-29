import json
import logging
import re
import unicodedata

from langchain_core.messages import HumanMessage, SystemMessage

from ai.prompts.supervisor_prompt import SUPERVISOR_PROMPT
from ai.services.action_state import clear_pending_action
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "action",
    "weekly_summary",
    "weekly_plan",
    "recommendations",
    "progress",
    "deep_research",
    "research",
    "document",
    "off_topic",
}

OFF_TOPIC_MESSAGE = (
    "Lo siento, solo puedo ayudarte con la gestion de tus proyectos, objetivos, "
    "tareas y calendario. ¿Hay algo relacionado en lo que pueda ayudarte?"
)

CONFIRM_WORDS = {"si", "confirmo", "confirmar", "adelante", "ejecuta", "ok", "vale"}
CANCEL_WORDS = {"no", "cancela", "cancelar", "anula", "detener"}


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip().lower()
    return ""


def _is_confirmation(user_text: str) -> bool:
    normalized = _normalize_confirmation_text(user_text)
    tokens = set(re.findall(r"\b\w+\b", normalized))
    return (
        normalized in CONFIRM_WORDS
        or normalized.startswith("confirm")
        or bool(tokens & CONFIRM_WORDS)
    )


def _is_cancellation(user_text: str) -> bool:
    normalized = _normalize_confirmation_text(user_text)
    tokens = set(re.findall(r"\b\w+\b", normalized))
    return (
        normalized in CANCEL_WORDS
        or normalized.startswith("cancel")
        or bool(tokens & CANCEL_WORDS)
    )


def _normalize_confirmation_text(user_text: str) -> str:
    text = (user_text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _parse_supervisor_json(text: str) -> dict:
    """Extrae el JSON de la respuesta del LLM supervisor."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return {}
    return {}


def _extract_docs_from_mutations(session_mutations_json: str) -> list[dict]:
    try:
        mutations = json.loads(session_mutations_json or "[]")
    except Exception:
        return []
    if not isinstance(mutations, list):
        return []

    docs = []
    seen = set()
    for item in mutations:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "document":
            continue
        if item.get("action") not in {"listed", "read", "created"}:
            continue
        doc_id = str(item.get("id") or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        description = item.get("description") or ""
        project_name = ""
        marker = "proyecto:"
        if marker in description.lower():
            project_name = description.split(":", 1)[1].strip()
        docs.append(
            {
                "_id": doc_id,
                "original_name": item.get("name") or "sin nombre",
                "_project_name": project_name,
            }
        )
    return docs


def _build_doc_list_for_resolver(docs: list[dict], context: dict) -> str:
    projects = {str(p.get("_id")): p for p in (context or {}).get("projects", [])}
    categories = {
        str(c.get("_id")): c.get("nombre") or c.get("name") or "sin categoria"
        for c in (context or {}).get("categories", [])
    }
    lines = []
    for doc in docs or []:
        project = projects.get(str(doc.get("project_id", "")))
        project_name = (
            (project or {}).get("titulo")
            or doc.get("_project_name")
            or "sin proyecto"
        )
        cat_ids = (project or {}).get("categorias") or []
        cat_names = [categories.get(str(cid), "sin categoria") for cid in cat_ids]
        category_text = ", ".join(cat_names) if cat_names else "sin categoría"
        lines.append(
            " | ".join(
                [
                    f"ID: {doc.get('_id', '')}",
                    f"Nombre: {doc.get('original_name') or doc.get('filename') or 'sin nombre'}",
                    f"Proyecto: {project_name}",
                    f"Categorias: {category_text}",
                ]
            )
        )
    return "\n".join(lines)


def _build_project_list_for_resolver(projects: list[dict]) -> str:
    lines = []
    for project in projects or []:
        lines.append(
            f"ID: {project.get('_id', '')} | Titulo: {project.get('titulo') or 'sin titulo'}"
        )
    return "\n".join(lines)


def supervisor_node(state: AppState, llm) -> AppState:
    """
    Doble fase:
      Fase 1 (Python puro): detectar confirmacion/cancelacion de acciones pendientes.
      Fase 2 (LLM): clasificar la intencion en 6 categorias. NO recibe context_json.
    """
    messages = state.get("messages", [])
    user_text = _last_user_text(messages)

    # Fase 1: Acciones pendientes 
    pending_action = state.get("pending_action_intent")
    if pending_action:
        # Caso especial: cola de acciones con confirmacion pendiente
        if pending_action.get("action_name") == "__queue__":
            if _is_confirmation(user_text):
                queue = pending_action.get("parameters", {}).get("queue", [])
                clear_pending_action(state.get("user_id"))
                return {
                    "route": "queue_executor",
                    "action_confirmed": True,
                    "action_queue": queue,
                    "action_results": [],
                    "action_ref_map": {},
                    "current_action_ref_id": None,
                    "action_result_id": None,
                    "action_result_message": None,
                    "pending_action_intent": None,
                }
            if _is_cancellation(user_text):
                clear_pending_action(state.get("user_id"))
                return {
                    "route": "finalize",
                    "pending_action_intent": None,
                    "action_confirmed": False,
                    "final_response": "Accion cancelada.",
                }
            return {
                "route": "finalize",
                "final_response": (
                    "Tienes acciones pendientes de confirmacion. "
                    "Responde 'confirmo' para ejecutarlas o 'cancela' para abortar."
                ),
                "pending_action_intent": pending_action,
            }

        # Caso normal: accion unica pendiente
        if _is_confirmation(user_text):
            return {"route": "action_executor", "action_confirmed": True}
        if _is_cancellation(user_text):
            clear_pending_action(state.get("user_id"))
            return {
                "route": "finalize",
                "pending_action_intent": None,
                "action_confirmed": False,
                "final_response": "Accion cancelada.",
            }
        return {
            "route": "finalize",
            "final_response": (
                "Tienes una accion pendiente. Responde 'confirmo' para ejecutarla "
                "o 'cancela' para abortar."
            ),
            "pending_action_intent": pending_action,
        }

    # Fase 2: Clasificacion LLM (sin context_json) 
    llm_messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
    ]
    llm_messages.extend(messages)

    try:
        raw = invoke_with_retry(llm, llm_messages)
    except LLMInvokeError:
        logger.exception("supervisor_node: error invocando LLM para clasificacion")
        return {"route": "research", "query_type": "research", "use_critic": False}

    parsed = _parse_supervisor_json(raw)
    category = parsed.get("category", "research")
    use_critic = parsed.get("use_critic", False)

    if category not in VALID_CATEGORIES:
        category = "research"

    if not isinstance(use_critic, bool):
        use_critic = False

    # Si es off_topic, inyectar respuesta fija y enrutar a finalize
    if category == "off_topic":
        return {
            "route": "finalize",
            "query_type": "off_topic",
            "use_critic": False,
            "final_response": OFF_TOPIC_MESSAGE,
        }

    result = {
        "route": category,
        "query_type": category,
        "use_critic": use_critic,
    }
    for key in (
        "context_needed",
        "doc_op",
        "doc_read_mode",
        "doc_target_id",
        "doc_target_ids",
        "doc_target_project_id",
        "doc_target_goal_id",
        "doc_analyze_points",
    ):
        if key in parsed:
            result[key] = parsed[key]
    return result


def route_after_supervisor(state: AppState) -> str:
    return state.get("route", "research")
