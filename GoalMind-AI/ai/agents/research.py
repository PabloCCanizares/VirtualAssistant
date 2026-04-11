import json
import logging

from langchain_core.messages import SystemMessage

from ai.prompts.research_prompt import RESEARCH_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.services.session_mutations_state import append_session_mutation
from ai.state import AppState


logger = logging.getLogger(__name__)


def _register_document_listings(user_id: str, context_json: str) -> None:
    """Registra en session_mutations los documentos de context_json como 'listed'."""
    if not user_id:
        return
    try:
        context = json.loads(context_json)
    except Exception:
        return
    projects_by_id = {str(p.get("_id", "")): p for p in context.get("projects", [])}
    for doc in context.get("documents", []):
        doc_id = str(doc.get("_id", ""))
        if not doc_id:
            continue
        name = doc.get("original_name") or doc.get("filename") or "sin nombre"
        project_id = str(doc.get("project_id", ""))
        project_title = projects_by_id.get(project_id, {}).get("titulo") or "sin proyecto"
        append_session_mutation(user_id, {
            "action": "listed",
            "type": "document",
            "id": doc_id,
            "name": name,
            "description": f"proyecto: {project_title}",
        })


def research_node(state: AppState, llm) -> AppState:
    context_json = state.get("context_json", "{}")
    messages = [
        SystemMessage(content=RESEARCH_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {context_json}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        notes = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("research_node: error invocando LLM")
        notes = ""

    _register_document_listings(state.get("user_id", ""), context_json)

    return {"research_notes": notes}
