from langchain_core.messages import HumanMessage, SystemMessage

from prompts.critic_prompt import CRITIC_PROMPT
from state import AppState


def critic_node(state: AppState, llm) -> AppState:
    draft = state.get("draft_response", "")
    messages = [
        SystemMessage(content=CRITIC_PROMPT),
        HumanMessage(content=f"Borrador para mejorar:\n\n{draft}"),
    ]
    response = llm.invoke(messages)
    return {"final_response": (response.content or "").strip()}
