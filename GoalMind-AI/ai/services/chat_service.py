import logging

from ai.config import get_settings
from database.mongo_conn import get_app_user_id
from ai.graph import run_graph_chat
from ai.services.action_state import get_pending_action
from ai.repositories.context_repository import get_user_context_json

logger = logging.getLogger(__name__)
DEFAULT_USER_ID = get_app_user_id()


def run_chat(message, history):
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("Mensaje vacio")

    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY no configurada")

    user_id = settings.default_user_id or DEFAULT_USER_ID
    try:
        context_json = get_user_context_json(user_id)
    except Exception:
        logger.exception("run_chat: error construyendo contexto de usuario")
        context_json = "{}"

    try:
        pending_action = get_pending_action(user_id)
    except Exception:
        logger.exception("run_chat: error recuperando accion pendiente")
        pending_action = None

    return run_graph_chat(
        user_message=user_message,
        history=list(history or []),
        context_json=context_json,
        model=settings.openai_model,
        user_id=user_id,
        pending_action_intent=pending_action,
    )
