import logging

from langchain_core.messages import SystemMessage

from ai.prompts.writer_prompt import WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def writer_node(state: AppState, llm) -> AppState:
    print("\n" + "="*60)
    print("WRITER_NODE: Formateando respuesta...")
    print("="*60)
    # Usa research_notes o progress_analysis, sin context_json crudo
    notes = state.get("research_notes") or state.get("progress_analysis", "")
    source = "research_notes" if state.get("research_notes") else "progress_analysis"
    print(f"   Origen de notas: {source} ({len(notes)} caracteres)")
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Notas de analisis:\n{notes}"),
    ]
    messages.extend(state.get("messages", []))
    print(f"   Llamando LLM para formatear respuesta...")
    try:
        draft = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("writer_node: error invocando LLM")
        draft = "No pude generar una respuesta en este momento."
    print(f"   ✓ Respuesta formateada ({len(draft)} caracteres)")
    print("="*60 + "\n")
    return {"draft_response": draft}
