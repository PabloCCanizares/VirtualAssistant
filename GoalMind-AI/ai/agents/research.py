import logging

from langchain_core.messages import SystemMessage

from ai.prompts.research_prompt import RESEARCH_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def research_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=RESEARCH_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        notes = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("research_node: error invocando LLM")
        notes = ""
    return {"research_notes": notes}
