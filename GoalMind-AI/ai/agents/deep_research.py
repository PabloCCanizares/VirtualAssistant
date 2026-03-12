import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ai.config import get_deep_search_config
from ai.prompts.deep_research_prompt import DEEP_RESEARCH_PROMPT
from ai.services.deep_search_service import DeepSearchError, deep_search
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def _last_user_message_text(messages) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip()
    return ""


def _to_sources(results: list[dict], max_sources: int) -> list[dict]:
    sources = []
    for item in (results or [])[:max_sources]:
        sources.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "score": item.get("score", 0.0),
                "provider": item.get("provider", ""),
            }
        )
    return sources


def deep_research_node(state: AppState, llm) -> AppState:
    print("\n" + "="*60)
    print("DEEP_RESEARCH_NODE: Ejecutando búsqueda profunda...")
    print("="*60)

    if not state.get("deep_search_requested", False):
        print("   ↷ deep_search_requested=False, no se ejecuta búsqueda profunda")
        print("="*60 + "\n")
        return {}

    query = _last_user_message_text(state.get("messages", []))
    if not query:
        print("   ✗ No hay query de usuario para deep research")
        print("="*60 + "\n")
        return {"deep_search_error": "No hay consulta para realizar búsqueda profunda."}

    try:
        config = get_deep_search_config()
        results = deep_search(query, config=config)
    except DeepSearchError as exc:
        logger.warning("deep_research_node: deep search no disponible: %s", exc)
        print(f"   ✗ Error deep search: {exc}")
        print("="*60 + "\n")
        return {"deep_search_error": str(exc), "deep_search_results": [], "deep_research_sources": []}
    except Exception as exc:
        logger.exception("deep_research_node: error inesperado en búsqueda profunda")
        print(f"   ✗ Error inesperado deep search: {exc}")
        print("="*60 + "\n")
        return {
            "deep_search_error": "No se pudo completar la búsqueda profunda.",
            "deep_search_results": [],
            "deep_research_sources": [],
        }

    sources = _to_sources(results, config.max_sources)
    if not sources:
        print("   ✗ No se encontraron fuentes útiles")
        print("="*60 + "\n")
        return {
            "deep_search_error": "No se encontraron fuentes relevantes en la búsqueda profunda.",
            "deep_search_results": results,
            "deep_research_sources": [],
        }

    prompt_messages = [
        SystemMessage(content=DEEP_RESEARCH_PROMPT),
        SystemMessage(content=f"Consulta del usuario: {query}"),
        SystemMessage(content=f"Fuentes (JSON): {json.dumps(sources, ensure_ascii=True)}"),
    ]
    prompt_messages.extend(state.get("messages", []))

    try:
        notes = invoke_with_retry(llm, prompt_messages, retries=1)
    except LLMInvokeError:
        logger.exception("deep_research_node: error invocando LLM")
        notes = ""

    print(f"   ✓ Fuentes recopiladas: {len(sources)}")
    print(f"   ✓ Notas de deep research: {len(notes)} caracteres")
    print("="*60 + "\n")
    return {
        "deep_search_error": "",
        "deep_search_results": results,
        "deep_research_sources": sources,
        "deep_research_notes": notes,
        # Compatibilidad futura: si se enruta a writer sin cambios adicionales
        "research_notes": notes or state.get("research_notes", ""),
    }
