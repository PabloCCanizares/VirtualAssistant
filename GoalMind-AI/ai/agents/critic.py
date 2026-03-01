import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ai.prompts.critic_prompt import CRITIC_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def critic_node(state: AppState, llm) -> AppState:
    draft = state.get("draft_response", "")
    messages = [
        SystemMessage(content=CRITIC_PROMPT),
        HumanMessage(content=f"Borrador para mejorar:\n\n{draft}"),
    ]
    try:
        final_text = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("critic_node: error invocando LLM")
        final_text = draft.strip() or "No pude generar una respuesta en este momento."
    return {"final_response": final_text}


