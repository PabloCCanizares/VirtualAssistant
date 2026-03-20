import logging

from langchain_core.messages import SystemMessage

from ai.prompts.progress_tracker_prompt import PROGRESS_TRACKER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def progress_tracker_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=PROGRESS_TRACKER_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        analysis = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("progress_tracker_node: error invocando LLM")
        analysis = ""
    return {"progress_analysis": analysis}
