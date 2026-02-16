from typing import TypedDict

from langchain_core.messages import BaseMessage


class AppState(TypedDict, total=False):
    messages: list[BaseMessage]
    context_json: str
    user_id: str
    route: str
    use_critic: bool
    fallback_route: str
    research_notes: str
    draft_response: str
    final_response: str
    action_name: str
    action_confidence: float
    action_parameters: dict
    action_needs_confirmation: bool
    action_clarification_question: str
    pending_action_intent: dict
    action_confirmed: bool
