import logging
from typing import Any, Iterable

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from ai.agents import (
    action_executor_node,
    action_planner_node,
    critic_node,
    deep_research_node,
    progress_tracker_node,
    queue_executor_node,
    recommendations_node,
    research_node,
    route_after_supervisor,
    supervisor_node,
    weekly_planner_node,
    weekly_summary_node,
    writer_node,
)
from ai.config import build_llm
from ai.state import AppState

logger = logging.getLogger(__name__)


def _history_to_messages(history: Iterable[dict[str, Any]] | None) -> list:
    messages = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


# ── Routing functions ──────────────────────────────────────────────


def _route_after_supervisor(state: AppState) -> str:
    """
    Mapea las categorias del supervisor a nodos del grafo.
    Posibles destinos:
      action           → action_planner  (nuevo flujo multi-accion)
      action_executor  → action_executor (accion unica pendiente confirmada)
      queue_executor   → queue_executor  (cola pendiente confirmada)
      weekly_summary   → weekly_summary
      weekly_plan      → weekly_planner
      recommendations  → recommendations
      progress         → progress_tracker
      deep_research    → deep_research
      research         → research
      off_topic        → finalize
      finalize         → finalize
    """
    route = route_after_supervisor(state)

    route_map = {
        "action": "action_planner",
        "action_executor": "action_executor",
        "queue_executor": "queue_executor",
        "weekly_summary": "weekly_summary",
        "weekly_plan": "weekly_planner",
        "recommendations": "recommendations",
        "progress": "progress_tracker",
        "deep_research": "deep_research",
        "research": "research",
        "off_topic": "finalize",
        "finalize": "finalize",
    }
    return route_map.get(route, "research")


def _route_after_action_planner(state: AppState) -> str:
    """
    Si action_planner puso una cola → queue_executor.
    Si pidio confirmacion o clarificacion → finalize.
    """
    if state.get("action_queue") is not None:
        return "queue_executor"
    return "finalize"


def _route_after_queue_executor(state: AppState) -> str:
    """
    Si queue_executor acaba de preparar una accion (action_name seteado) → action_executor.
    Si la cola estaba vacia y ya construyo el resumen (action_name=None) → finalize.
    """
    if state.get("action_name"):
        return "action_executor"
    return "finalize"


def _route_after_action_executor(state: AppState) -> str:
    """
    Si estamos en modo cola (action_queue fue inicializado) → volver a queue_executor.
    En modo simple (action_queue es None) → finalize directamente.
    """
    if state.get("action_queue") is not None:
        return "queue_executor"
    return "finalize"


def _route_after_writer(state: AppState) -> str:
    return "critic" if state.get("use_critic", False) else "finalize"


def _route_after_deep_research(state: AppState) -> str:
    """
    Si deep_research falla o no aporta notas, hacemos fallback a research.
    Si hay notas válidas, continuamos con writer.
    """
    if (state.get("deep_search_error") or "").strip():
        return "research"

    notes = (state.get("deep_research_notes") or state.get("research_notes") or "").strip()
    if notes:
        return "writer"
    return "research"


def _finalize_node(state: AppState) -> AppState:
    print("\n" + "="*60)
    print("✅ FINALIZE_NODE: Finalizando respuesta...")
    print("="*60)
    final_response = (state.get("final_response") or "").strip()
    deep_search_error = (state.get("deep_search_error") or "").strip()
    deep_search_mode = (state.get("deep_search_mode") or "").strip().lower()
    deep_search_notice = ""
    if deep_search_error and deep_search_mode != "off":
        deep_search_notice = (
            "Aviso: no se pudo completar la busqueda profunda. "
            f"Motivo: {deep_search_error}"
        )

    if final_response:
        if deep_search_notice and deep_search_notice not in final_response:
            final_response = f"{deep_search_notice}\n\n{final_response}"
        print(f"   ✓ final_response ya establecido ({len(final_response)} caracteres)")
        print("="*60 + "\n")
        return {"final_response": final_response}

    draft = (state.get("draft_response") or "").strip()
    if not draft:
        draft = "No pude generar una respuesta en este momento."
    if deep_search_notice and deep_search_notice not in draft:
        draft = f"{deep_search_notice}\n\n{draft}"
    print(f"   ✓ Usando draft_response como final ({len(draft)} caracteres)")
    print("="*60 + "\n")
    return {"final_response": draft}


# ── Graph builder ──────────────────────────────────────────────────


def build_chat_graph(llm):
    graph = StateGraph(AppState)

    # Nodos
    graph.add_node("supervisor", lambda state: supervisor_node(state, llm))
    graph.add_node("action_planner", lambda state: action_planner_node(state, llm))
    graph.add_node("queue_executor", lambda state: queue_executor_node(state, llm))
    graph.add_node("action_executor", lambda state: action_executor_node(state, llm))
    graph.add_node("deep_research", lambda state: deep_research_node(state, llm))
    graph.add_node("research", lambda state: research_node(state, llm))
    graph.add_node("recommendations", lambda state: recommendations_node(state, llm))
    graph.add_node("weekly_summary", lambda state: weekly_summary_node(state, llm))
    graph.add_node("weekly_planner", lambda state: weekly_planner_node(state, llm))
    graph.add_node("progress_tracker", lambda state: progress_tracker_node(state, llm))
    graph.add_node("writer", lambda state: writer_node(state, llm))
    graph.add_node("critic", lambda state: critic_node(state, llm))
    graph.add_node("finalize", _finalize_node)

    # START → supervisor
    graph.add_edge(START, "supervisor")

    # supervisor → destinos
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "action_planner": "action_planner",
            "action_executor": "action_executor",
            "queue_executor": "queue_executor",
            "weekly_summary": "weekly_summary",
            "weekly_planner": "weekly_planner",
            "recommendations": "recommendations",
            "progress_tracker": "progress_tracker",
            "deep_research": "deep_research",
            "research": "research",
            "finalize": "finalize",
        },
    )

    # deep_research → writer (si hay notas) o research (fallback)
    graph.add_conditional_edges(
        "deep_research",
        _route_after_deep_research,
        {
            "writer": "writer",
            "research": "research",
        },
    )

    # action_planner → queue_executor (cola lista) o finalize (confirmacion/clarificacion)
    graph.add_conditional_edges(
        "action_planner",
        _route_after_action_planner,
        {
            "queue_executor": "queue_executor",
            "finalize": "finalize",
        },
    )

    # queue_executor → action_executor (cola no vacia) o finalize (cola vacia)
    graph.add_conditional_edges(
        "queue_executor",
        _route_after_queue_executor,
        {
            "action_executor": "action_executor",
            "finalize": "finalize",
        },
    )

    # action_executor → queue_executor (modo cola) o finalize (modo simple)
    graph.add_conditional_edges(
        "action_executor",
        _route_after_action_executor,
        {
            "queue_executor": "queue_executor",
            "finalize": "finalize",
        },
    )

    # weekly_summary → finalize (directo, opcionalmente via critic)
    graph.add_conditional_edges(
        "weekly_summary",
        _route_after_writer,
        {"critic": "critic", "finalize": "finalize"},
    )

    # weekly_planner → finalize (directo, opcionalmente via critic)
    graph.add_conditional_edges(
        "weekly_planner",
        _route_after_writer,
        {"critic": "critic", "finalize": "finalize"},
    )

    # recommendations → finalize (directo, opcionalmente via critic)
    graph.add_conditional_edges(
        "recommendations",
        _route_after_writer,
        {"critic": "critic", "finalize": "finalize"},
    )

    # research → writer (siempre pasa por writer)
    graph.add_edge("research", "writer")

    # progress_tracker → writer (siempre pasa por writer)
    graph.add_edge("progress_tracker", "writer")

    # writer → critic o finalize
    graph.add_conditional_edges(
        "writer",
        _route_after_writer,
        {"critic": "critic", "finalize": "finalize"},
    )

    # critic → finalize
    graph.add_edge("critic", "finalize")

    # finalize → END
    graph.add_edge("finalize", END)

    return graph.compile()


def run_graph_chat(
    user_message: str,
    history,
    context_json: str,
    model: str,
    user_id: str,
    pending_action_intent: dict | None = None,
    session_mutations_json: str = "[]",
    deep_search_mode: str = "auto",
    deep_search_requested: bool = False,
    deep_search_error: str = "",
) -> str:
    print("\n" + "#"*60)
    print("# INICIANDO GRAFO DE CHAT")
    print("#"*60)
    print(f"   Usuario: {user_id}")
    print(f"   Modelo: {model}")
    print(f"   Mensaje: '{user_message[:80]}{'...' if len(user_message) > 80 else ''}'")
    print(f"   Historial: {len(history)} mensajes")
    print(f"   Accion pendiente: {'Sí' if pending_action_intent else 'No'}")
    print("#"*60 + "\n")

    llm = build_llm(model)
    app = build_chat_graph(llm)

    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "context_json": context_json or "{}",
        "user_id": user_id,
        "pending_action_intent": pending_action_intent,
        "session_mutations_json": session_mutations_json,
        "deep_search_mode": deep_search_mode,
        "deep_search_requested": deep_search_requested,
        "deep_search_error": deep_search_error,
    }
    try:
        result = app.invoke(state, config={"recursion_limit": 50})
    except Exception as exc:
        logger.exception("run_graph_chat: fallo en ejecucion del grafo")
        raise RuntimeError("No se pudo ejecutar el flujo de chat.") from exc

    final_response = (result.get("final_response") or "").strip()
    print("#"*60)
    print("#GRAFO COMPLETADO")
    print("#"*60)
    print(f"   Respuesta final ({len(final_response)} caracteres):")
    print(f"   {final_response[:100]}{'...' if len(final_response) > 100 else ''}")
    print("#"*60 + "\n")
    return final_response
