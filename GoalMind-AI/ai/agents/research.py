import logging
import json

from langchain_core.messages import SystemMessage

from ai.prompts.research_prompt import RESEARCH_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def _register_document_listings(user_id: str, context_json: str) -> None:
    """
    Compatibilidad con el flujo anterior de research.
    Acepta contextos con proyectos/documentos y no interrumpe el chat si llegan mal formados.
    """
    if not user_id:
        return
    try:
        context = json.loads(context_json or "{}")
    except Exception:
        return
    if not isinstance(context, dict):
        return
    projects = context.get("projects") or []
    documents = context.get("documents") or []
    if not projects and not documents:
        return
    logger.debug(
        "research_node: listado disponible para usuario %s (%s proyectos, %s documentos)",
        user_id,
        len(projects) if isinstance(projects, list) else 0,
        len(documents) if isinstance(documents, list) else 0,
    )


def research_node(state: AppState, llm) -> AppState:
    _register_document_listings(state.get("user_id", ""), state.get("context_json", "{}"))
    messages = [
        SystemMessage(content=RESEARCH_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        notes = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("research_node: error invocando LLM")
        notes = ""
    return {"research_notes": notes}

