import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ai.prompts.supervisor_prompt import SUPERVISOR_PROMPT
from ai.services.action_state import clear_pending_action
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"action", "weekly_summary", "weekly_plan", "recommendations", "progress", "research", "off_topic"}

OFF_TOPIC_MESSAGE = (
    "Lo siento, solo puedo ayudarte con la gestion de tus proyectos, objetivos, "
    "tareas y calendario. ¿Hay algo relacionado en lo que pueda ayudarte?"
)

CONFIRM_WORDS = {"si", "sí", "confirmo", "confirmar", "adelante", "ejecuta", "ok", "vale"}
CANCEL_WORDS = {"no", "cancela", "cancelar", "anula", "detener"}


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip().lower()
    return ""


def _is_confirmation(user_text: str) -> bool:
    normalized = (user_text or "").strip().lower()
    return normalized in CONFIRM_WORDS or normalized.startswith("confirm")


def _is_cancellation(user_text: str) -> bool:
    normalized = (user_text or "").strip().lower()
    return normalized in CANCEL_WORDS or normalized.startswith("cancel")


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


def supervisor_node(state: AppState, llm) -> AppState:
    """
    Doble fase:
      Fase 1 (Python puro): detectar confirmacion/cancelacion de acciones pendientes.
      Fase 2 (LLM): clasificar la intencion en 6 categorias. NO recibe context_json.
    """
    print("\n" + "="*60)
    print("SUPERVISOR_NODE: Clasificando intencion del usuario...")
    print("="*60)
    messages = state.get("messages", [])
    user_text = _last_user_text(messages)
    print(f"   Ultimo mensaje del usuario: '{user_text}'")
    print(f"   ¿Hay accion pendiente? {bool(state.get('pending_action_intent'))}")

    # ── Fase 1: Acciones pendientes (Python puro) ──────────────────
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

    # ── Fase 2: Clasificacion LLM (sin context_json) ──────────────
    llm_messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
    ]
    llm_messages.extend(messages)

    try:
        raw = invoke_with_retry(llm, llm_messages, retries=1)
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
        print(f"\n   ✓ RUTA DECIDIDA: 'finalize' (off_topic)")
        print("="*60 + "\n")
        return {
            "route": "finalize",
            "query_type": "off_topic",
            "use_critic": False,
            "final_response": OFF_TOPIC_MESSAGE,
        }

    print(f"\n   ✓ RUTA DECIDIDA: '{category}' (use_critic={use_critic})")
    print("="*60 + "\n")
    return {
        "route": category,
        "query_type": category,
        "use_critic": use_critic,
    }


def route_after_supervisor(state: AppState) -> str:
    return state.get("route", "research")
