from langchain_core.messages import SystemMessage

from prompts.research_prompt import RESEARCH_PROMPT
from state import AppState


def research_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=RESEARCH_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    response = llm.invoke(messages)
    return {"research_notes": (response.content or "").strip()}
