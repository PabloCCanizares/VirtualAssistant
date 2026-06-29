import logging

from langchain_core.messages import HumanMessage

from ai.config import get_settings, resolve_chat_model
from database.mongo_conn import get_app_user_id
from ai.graph import _history_to_messages, build_chat_graph, build_llm, run_graph_chat
from ai.services.node_status import NODE_STATUS
from ai.services.action_state import get_pending_action
from ai.services.session_mutations_state import get_session_mutations_json

logger = logging.getLogger(__name__)
DEFAULT_USER_ID = get_app_user_id()


def _resolve_deep_search_mode(settings, requested):
    valid_modes = {"auto", "on", "off"}
    mode = (requested or "").strip().lower()
    if not mode:
        mode = (getattr(settings, "deep_search_mode_default", "auto") or "auto").strip().lower()
    return mode if mode in valid_modes else "auto"


def _validate_provider_key(settings, provider):
    key_by_provider = {
        "openai": ("openai_api_key", "OPENAI_API_KEY"),
        "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
        "groq": ("groq_api_key", "GROQ_API_KEY"),
    }
    attr, env_key = key_by_provider.get(provider, (None, "API_KEY"))
    if not attr or not (getattr(settings, attr, None) or "").strip():
        raise ValueError(f"Falta {env_key} para usar el proveedor {provider}.")


def run_chat(message, history, model_id=None, deep_search_mode=None):
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("Mensaje vacio")

    settings = get_settings()
    selected_model = resolve_chat_model(settings, model_id or getattr(settings, "llm_provider", None))
    _validate_provider_key(settings, selected_model.provider)

    resolved_deep_search_mode = _resolve_deep_search_mode(settings, deep_search_mode)
    deep_search_requested = bool(getattr(settings, "deep_search_enabled", False) and resolved_deep_search_mode == "on")
    deep_search_error = ""
    if resolved_deep_search_mode == "on" and not getattr(settings, "deep_search_enabled", False):
        deep_search_error = "Deep search deshabilitado en la configuracion."

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
        model=selected_model.model,
        provider=selected_model.provider,
        api_key=selected_model.api_key,
        user_id=user_id,
        pending_action_intent=pending_action,
        session_mutations_json=session_mutations_json,
        timeout_seconds=getattr(settings, "openai_timeout_seconds", 25),
        deep_search_mode=resolved_deep_search_mode,
        deep_search_requested=deep_search_requested,
        deep_search_error=deep_search_error,
    )


def stream_chat(message, history, model_id=None, deep_search_mode=None):
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("Mensaje vacio")

    settings = get_settings()
    selected_model = resolve_chat_model(settings, model_id or getattr(settings, "llm_provider", None))
    _validate_provider_key(settings, selected_model.provider)

    resolved_deep_search_mode = _resolve_deep_search_mode(settings, deep_search_mode)
    deep_search_requested = bool(getattr(settings, "deep_search_enabled", False) and resolved_deep_search_mode == "on")
    deep_search_error = ""
    if resolved_deep_search_mode == "on" and not getattr(settings, "deep_search_enabled", False):
        deep_search_error = "Deep search deshabilitado en la configuracion."

    user_id = settings.default_user_id or DEFAULT_USER_ID
    try:
        pending_action = get_pending_action(user_id)
    except Exception:
        logger.exception("stream_chat: error recuperando accion pendiente")
        pending_action = None

    try:
        session_mutations_json = get_session_mutations_json(user_id)
    except Exception:
        logger.exception("stream_chat: error recuperando mutaciones de sesion")
        session_mutations_json = "[]"

    try:
        llm = build_llm(
            provider=selected_model.provider,
            model=selected_model.model,
            api_key=selected_model.api_key,
            timeout_seconds=getattr(settings, "openai_timeout_seconds", 25),
        )
    except TypeError:
        llm = build_llm(model=selected_model.model)

    app = build_chat_graph(llm)
    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "user_id": user_id,
        "pending_action_intent": pending_action,
        "session_mutations_json": session_mutations_json,
        "deep_search_mode": resolved_deep_search_mode,
        "deep_search_requested": deep_search_requested,
        "deep_search_error": deep_search_error,
    }

    final_reply = ""
    try:
        for update in app.stream(state, config={"recursion_limit": 50}, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_id, changes in update.items():
                status = NODE_STATUS.get(node_id)
                if status:
                    yield ("status", {"node": node_id, **status})
                if isinstance(changes, dict) and changes.get("final_response"):
                    final_reply = (changes.get("final_response") or "").strip()
        yield ("done", {"reply": final_reply})
    except BaseException as exc:
        logger.exception("stream_chat: fallo en ejecucion del grafo")
        yield ("error", {"message": f"Error al generar respuesta: {exc}"})
