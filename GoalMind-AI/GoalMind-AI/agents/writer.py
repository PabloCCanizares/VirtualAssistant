from langchain_core.messages import SystemMessage

from prompts.writer_prompt import WRITER_PROMPT
from state import AppState


def writer_node(state: AppState, llm) -> AppState:
    research_notes = state.get("research_notes", "")
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
        SystemMessage(content=f"Research: {research_notes}"),
    ]
    messages.extend(state.get("messages", []))
    response = llm.invoke(messages)
    return {"draft_response": (response.content or "").strip()}
