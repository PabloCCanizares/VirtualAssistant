import logging

from langchain_core.messages import HumanMessage

from ai.config import get_deep_research_runtime_config, get_deep_search_config
from ai.deep_research import run_deep_research
from ai.services.deep_search_service import DeepSearchError, deep_search
from ai.state import AppState


logger = logging.getLogger(__name__)


def _last_user_message_text(messages) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return (message.content or "").strip()
    return ""


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
        runtime_config = get_deep_research_runtime_config()
        result = run_deep_research(
            user_query=query,
            context_json=state.get("context_json", "{}"),
            llm=llm,
            search_config=config,
            runtime_config=runtime_config,
            web_search_tool=deep_search,
        )
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

    if result.error:
        print(f"   ✗ Error deep research: {result.error}")
        print("="*60 + "\n")
        return {
            "deep_search_error": result.error,
            "deep_search_results": result.raw_results,
            "deep_research_sources": result.sources,
            "deep_research_plan": result.plan,
            "deep_research_iterations": result.iterations,
            "deep_research_warnings": result.warnings,
        }

    notes = (result.report or "").strip()
    if not notes:
        print("   ✗ No se encontraron fuentes útiles")
        print("="*60 + "\n")
        return {
            "deep_search_error": "No se encontraron fuentes relevantes en la búsqueda profunda.",
            "deep_search_results": result.raw_results,
            "deep_research_sources": [],
        }

    print(f"   ✓ Fuentes recopiladas: {len(result.sources)}")
    print(f"   ✓ Notas de deep research: {len(notes)} caracteres")
    print("="*60 + "\n")
    return {
        "deep_search_error": "",
        "deep_search_results": result.raw_results,
        "deep_research_sources": result.sources,
        "deep_research_notes": notes,
        "deep_research_plan": result.plan,
        "deep_research_iterations": result.iterations,
        "deep_research_warnings": result.warnings,
        # Compatibilidad futura: si se enruta a writer sin cambios adicionales
        "research_notes": notes or state.get("research_notes", ""),
    }
