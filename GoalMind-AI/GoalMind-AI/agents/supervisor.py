from langchain_core.messages import HumanMessage, SystemMessage

from prompts.supervisor_prompt import SUPERVISOR_PROMPT
from state import AppState


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip().lower()
    return ""


def supervisor_node(state: AppState, llm) -> AppState:
    user_text = _last_user_text(state.get("messages", []))
    fast_words = ["rapido", "breve", "resumen", "corto"]
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

    if any(word in user_text for word in recommendation_words):
        route = "recommendations"
    elif any(word in user_text for word in fast_words):
        route = "writer"
    else:
        route = "research"

    messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"Mensaje usuario: {user_text}"),
    ]
    _ = llm.invoke(messages)

    return {"route": route, "use_critic": use_critic}


def route_after_supervisor(state: AppState) -> str:
    return state.get("route", "research")
