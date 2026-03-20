"""Nodo lector de documentos (LLM).

Recibe el texto extraido del documento y genera una respuesta segun
el modo de lectura: full, summary o analyze.
"""

import logging

from langchain_core.messages import SystemMessage

from ai.prompts.doc_reader_prompt import (
    DOC_READER_ANALYZE_PROMPT,
    DOC_READER_FULL_PROMPT,
    DOC_READER_SUMMARY_PROMPT,
)
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.services.session_mutations_state import append_session_mutation
from ai.state import AppState

logger = logging.getLogger(__name__)

_MODE_PROMPTS = {
    "full": DOC_READER_FULL_PROMPT,
    "summary": DOC_READER_SUMMARY_PROMPT,
    "analyze": DOC_READER_ANALYZE_PROMPT,
}


def doc_reader_node(state: AppState, llm) -> AppState:
    doc_name = state.get("doc_target_name", "documento")
    read_mode = state.get("doc_read_mode", "full")
    text_content = state.get("doc_content_text", "")
    analyze_points = state.get("doc_analyze_points", "")

    if not text_content:
        msg = f"No hay contenido de texto disponible para el documento '{doc_name}'."
        return {"draft_response": msg}

    base_prompt = _MODE_PROMPTS.get(read_mode, DOC_READER_FULL_PROMPT)

    if read_mode == "analyze" and analyze_points:
        base_prompt += f"\n\nEl usuario quiere que analices especificamente: {analyze_points}"

    messages = [
        SystemMessage(content=base_prompt),
        SystemMessage(content=f"Nombre del documento: {doc_name}\n\nContenido:\n{text_content}"),
    ]
    messages.extend(state.get("messages", []))

    try:
        response = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("doc_reader_node: error invocando LLM")
        response = f"No pude procesar el documento '{doc_name}' en este momento."

    mode_labels = {"full": "lectura completa", "summary": "resumen", "analyze": "analisis"}
    description = f"{mode_labels.get(read_mode, read_mode)} de '{doc_name}'"
    if read_mode == "analyze" and analyze_points:
        description += f" ({analyze_points[:80]})"

    append_session_mutation(state.get("user_id", ""), {
        "action": "read",
        "type": "document",
        "id": state.get("doc_target_id", ""),
        "name": doc_name,
        "description": description,
    })

    return {"draft_response": response}
