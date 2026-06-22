import logging

from langchain_core.messages import SystemMessage

from ai.prompts.recommendations_prompt import RECOMMENDATIONS_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def recommendations_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=RECOMMENDATIONS_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("recommendations_node: error invocando LLM")
        draft = "No pude generar recomendaciones en este momento."
    return {"draft_response": draft}
