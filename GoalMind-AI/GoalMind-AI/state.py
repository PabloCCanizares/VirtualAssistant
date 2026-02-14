from typing import TypedDict

from langchain_core.messages import BaseMessage


class AppState(TypedDict, total=False):
    messages: list[BaseMessage]
    context_json: str
    route: str
    use_critic: bool
    research_notes: str
    draft_response: str
    final_response: str
