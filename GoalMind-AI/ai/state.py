from typing import Any, TypedDict

from langchain_core.messages import BaseMessage


class ActionIntent(TypedDict, total=False):
    action_name: str
    parameters: dict[str, Any]


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
    action_parameters: dict[str, Any]
    action_needs_confirmation: bool
    action_clarification_question: str
    pending_action_intent: ActionIntent
    action_confirmed: bool
