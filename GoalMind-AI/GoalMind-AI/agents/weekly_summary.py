from langchain_core.messages import SystemMessage

from prompts.weekly_summary_prompt import WEEKLY_SUMMARY_PROMPT
from state import AppState


def weekly_summary_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=WEEKLY_SUMMARY_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    response = llm.invoke(messages)
    return {"draft_response": (response.content or "").strip()}
