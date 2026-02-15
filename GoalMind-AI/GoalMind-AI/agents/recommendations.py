from langchain_core.messages import SystemMessage

from prompts.recommendations_prompt import RECOMMENDATIONS_PROMPT
from state import AppState


def recommendations_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=RECOMMENDATIONS_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    response = llm.invoke(messages)
    return {"draft_response": (response.content or "").strip()}
