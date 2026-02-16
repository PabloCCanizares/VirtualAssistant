from langchain_core.messages import HumanMessage
from services.action_state import clear_pending_action
from state import AppState


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip().lower()
    return ""


def supervisor_node(state: AppState, llm) -> AppState:
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
        confirm_words = {"si", "sí", "confirmo", "confirmar", "adelante", "ejecuta", "ok", "vale"}
        cancel_words = {"no", "cancela", "cancelar", "anula", "detener"}
        if user_text in confirm_words or user_text.startswith("confirm"):
            return {"route": "action_executor", "action_confirmed": True}
        if user_text in cancel_words or user_text.startswith("cancel"):
            clear_pending_action(state.get("user_id"))
            return {"route": "finalize", "final_response": "Acción cancelada."}
        # Si el usuario escribe otra cosa, se limpia la acción pendiente
        clear_pending_action(state.get("user_id"))

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
