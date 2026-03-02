import logging

from ai.config import get_settings
from database.mongo_conn import get_app_user_id
from ai.graph import run_graph_chat
from ai.services.action_state import get_pending_action
from ai.services.session_mutations_state import get_session_mutations_json

logger = logging.getLogger(__name__)
DEFAULT_USER_ID = get_app_user_id()


def run_chat(message, history):
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("Mensaje vacio")

    settings = get_settings()
    provider = settings.ai_provider
    model = settings.openai_model
    api_key = settings.openai_api_key
    base_url = None
    if provider == "groq":
        model = settings.groq_model
        api_key = settings.groq_api_key
        base_url = "https://api.groq.com/openai/v1"
        if not api_key:
            raise ValueError("GROQ_API_KEY no configurada")
    else:
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada")

    user_id = settings.default_user_id or DEFAULT_USER_ID
    try:
        pending_action = get_pending_action(user_id)
    except Exception:
        logger.exception("run_chat: error recuperando accion pendiente")
        pending_action = None

    try:
        session_mutations_json = get_session_mutations_json(user_id)
    except Exception:
        logger.exception("run_chat: error recuperando mutaciones de sesion")
        session_mutations_json = "[]"

    return run_graph_chat(
        user_message=user_message,
        history=list(history or []),
        model=model,
        user_id=user_id,
        pending_action_intent=pending_action,
        session_mutations_json=session_mutations_json,
        timeout_seconds=settings.openai_timeout_seconds,
        api_key=api_key,
        base_url=base_url,
    )
