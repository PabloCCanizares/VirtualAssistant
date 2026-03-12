import logging

from ai.config import get_settings
from database.mongo_conn import get_app_user_id
from ai.graph import run_graph_chat
from ai.services.action_state import get_pending_action
from ai.services.session_mutations_state import get_session_mutations_json
from ai.repositories.context_repository import get_user_context_json

logger = logging.getLogger(__name__)
DEFAULT_USER_ID = get_app_user_id()
ALLOWED_DEEP_SEARCH_MODES = {"auto", "on", "off"}


def _resolve_deep_search_mode(settings, requested_mode):
    mode = (requested_mode or "").strip().lower()
    if not mode:
        mode = (settings.deep_search_mode_default or "auto").strip().lower()
    if mode not in ALLOWED_DEEP_SEARCH_MODES:
        mode = "auto"
    return mode


def run_chat(message, history, deep_search_mode=None):
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("Mensaje vacio")

    settings = get_settings()
    if settings.llm_provider == "gemini" and not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY no configurada")
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY no configurada")
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY no configurada")

    if settings.llm_provider == "gemini":
        selected_model = settings.gemini_model
    elif settings.llm_provider == "groq":
        selected_model = settings.groq_model
    else:
        selected_model = settings.openai_model

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

    try:
        session_mutations_json = get_session_mutations_json(user_id)
    except Exception:
        logger.exception("run_chat: error recuperando mutaciones de sesion")
        session_mutations_json = "[]"

    resolved_deep_search_mode = _resolve_deep_search_mode(settings, deep_search_mode)
    deep_search_requested = settings.deep_search_enabled and resolved_deep_search_mode == "on"
    deep_search_error = (
        "Deep search deshabilitado por configuración."
        if resolved_deep_search_mode == "on" and not settings.deep_search_enabled
        else ""
    )

    return run_graph_chat(
        user_message=user_message,
        history=list(history or []),
        context_json=context_json,
        model=selected_model,
        user_id=user_id,
        pending_action_intent=pending_action,
        session_mutations_json=session_mutations_json,
        deep_search_mode=resolved_deep_search_mode,
        deep_search_requested=deep_search_requested,
        deep_search_error=deep_search_error,
    )
