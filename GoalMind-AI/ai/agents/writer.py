import logging

from langchain_core.messages import SystemMessage

from ai.prompts.writer_prompt import WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def writer_node(state: AppState, llm) -> AppState:
    research_notes = state.get("research_notes", "")
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
        SystemMessage(content=f"Research: {research_notes}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("writer_node: error invocando LLM")
        draft = "No pude generar una respuesta en este momento."
    return {"draft_response": draft}
