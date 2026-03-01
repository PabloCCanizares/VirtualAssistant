import logging

from langchain_core.messages import SystemMessage

from ai.prompts.writer_prompt import WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def writer_node(state: AppState, llm) -> AppState:
    # Usa research_notes o progress_analysis, sin context_json crudo
    notes = state.get("research_notes") or state.get("progress_analysis", "")
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Notas de analisis:\n{notes}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("writer_node: error invocando LLM")
        draft = "No pude generar una respuesta en este momento."
    return {"draft_response": draft}


