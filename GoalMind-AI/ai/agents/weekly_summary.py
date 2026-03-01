import logging

from langchain_core.messages import SystemMessage

from ai.prompts.weekly_summary_prompt import WEEKLY_SUMMARY_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def weekly_summary_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=WEEKLY_SUMMARY_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("weekly_summary_node: error invocando LLM")
        draft = "No pude generar el resumen semanal en este momento."
    return {"draft_response": draft}


