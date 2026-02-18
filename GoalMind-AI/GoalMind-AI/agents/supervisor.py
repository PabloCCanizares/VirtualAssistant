from langchain_core.messages import HumanMessage
from services.action_state import clear_pending_action
from state import AppState

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


def supervisor_node(state: AppState, _llm) -> AppState:
    user_text = _last_user_text(state.get("messages", []))
    fast_words = ["rapido", "breve", "resumen", "corto"]
    weekly_summary_exact_trigger = "hazme un resumen de la semana"
    recommendation_words = [
        "recomendacion",
        "recomendaciones",
        "recomiendame",
        "dame recomendaciones",
        "recomendaciones personales",
        "priorizar",
        "prioridades",
    ]
    use_critic = any(word in user_text for word in ["critica", "mejora", "revisa"])

    pending_action = state.get("pending_action_intent")
    if pending_action:
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

    if any(word in user_text for word in recommendation_words):
        fallback = "recommendations"
    elif user_text == weekly_summary_exact_trigger:
        fallback = "weekly_summary"
    elif any(word in user_text for word in fast_words):
        fallback = "writer"
    else:
        fallback = "research"

    return {
        "route": "intent_interpreter",
        "fallback_route": fallback,
        "use_critic": use_critic,
    }


def route_after_supervisor(state: AppState) -> str:
    return state.get("route", "intent_interpreter")
