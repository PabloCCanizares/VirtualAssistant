from config import get_settings
from database.mongo_conn import get_app_user_id
from graph import run_graph_chat
from services.action_state import get_pending_action
from repositories.context_repository import get_user_context_json

DEFAULT_USER_ID = get_app_user_id()


def run_chat(message, history):
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY no configurada")

    user_id = settings.default_user_id or DEFAULT_USER_ID
    context_json = get_user_context_json(user_id)
    pending_action = get_pending_action(user_id)

    return run_graph_chat(
        user_message=message,
        history=history,
        context_json=context_json,
        model=settings.openai_model,
        user_id=user_id,
        pending_action_intent=pending_action,
    )
