import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ai.prompts.critic_prompt import CRITIC_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


def critic_node(state: AppState, llm) -> AppState:
    print("\n" + "="*60)
    print("CRITIC_NODE: Revisando y mejorando respuesta...")
    print("="*60)
    draft = state.get("draft_response", "")
    print(f"   Borrador recibido ({len(draft)} caracteres)")
    messages = [
        SystemMessage(content=CRITIC_PROMPT),
        HumanMessage(content=f"Borrador para mejorar:\n\n{draft}"),
    ]
    print(f"   Llamando LLM para revision y mejora...")
    try:
        final_text = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("critic_node: error invocando LLM")
        final_text = draft.strip() or "No pude generar una respuesta en este momento."
    print(f"   ✓ Respuesta mejorada ({len(final_text)} caracteres)")
    print("="*60 + "\n")
    return {"final_response": final_text}
