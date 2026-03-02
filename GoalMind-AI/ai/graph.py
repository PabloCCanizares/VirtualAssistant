import logging
from typing import Any, Iterable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from ai.agents import (
    action_executor_node,
    action_planner_node,
    critic_node,
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
from ai.repositories.context_repository import (
    get_user_context_json,
    get_weekly_planner_context_json,
    get_weekly_due_context_json,
)
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
    Si quedan acciones en la cola → action_executor.
    Si la cola esta vacia → finalize.
    """
    queue = state.get("action_queue") or []
    if queue:
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


def _route_after_context_loader(state: AppState) -> str:
    """
    Reenvia al nodo correcto despues de asegurar que el contexto esta cargado.
    """
    route = state.get("route", "research")
    route_map = {
        "action": "action_planner",
        "action_executor": "action_executor",
        "weekly_summary": "weekly_summary",
        "weekly_plan": "weekly_planner",
        "recommendations": "recommendations",
        "progress": "progress_tracker",
        "research": "research",
    }
    return route_map.get(route, "research")


def _ensure_context_node(state: AppState) -> AppState:
    """
    Carga el contexto solo cuando algun nodo lo necesita.
    Si ya existe en state, se reutiliza.
    """
    cached = (state.get("context_json") or "").strip()
    if cached:
        return {"context_json": cached}

    user_id = state.get("user_id")
    if not user_id:
        return {"context_json": "{}"}

    try:
        context_json = get_user_context_json(user_id)
    except Exception:
        logger.exception("_ensure_context_node: error construyendo contexto de usuario")
        context_json = "{}"
    return {"context_json": context_json}


def _ensure_weekly_summary_context_node(state: AppState) -> AppState:
    """
    Carga contexto filtrado para weekly_summary:
    solo vencimientos/eventos de la semana.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"context_json": "{}"}

    try:
        context_json = get_weekly_due_context_json(user_id)
    except Exception:
        logger.exception("_ensure_weekly_summary_context_node: error construyendo contexto semanal")
        context_json = "{}"
    return {"context_json": context_json}


def _ensure_weekly_planner_context_node(state: AppState) -> AppState:
    """
    Carga contexto filtrado para weekly_planner:
    solo vencimientos/eventos de los proximos 7 dias.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"context_json": "{}"}

    try:
        context_json = get_weekly_planner_context_json(user_id)
    except Exception:
        logger.exception("_ensure_weekly_planner_context_node: error construyendo contexto de plan semanal")
        context_json = "{}"
    return {"context_json": context_json}


def _finalize_node(state: AppState) -> AppState:
    final_response = (state.get("final_response") or "").strip()
    if final_response:
        return {"final_response": final_response}

    draft = (state.get("draft_response") or "").strip()
    if not draft:
        draft = "No pude generar una respuesta en este momento."
    return {"final_response": draft}


# ── Graph builder ──────────────────────────────────────────────────


def build_chat_graph(llm):
    graph = StateGraph(AppState)

    # Nodos
    graph.add_node("supervisor", lambda state: supervisor_node(state, llm))
    graph.add_node("load_context", _ensure_context_node)
    graph.add_node("load_weekly_summary_context", _ensure_weekly_summary_context_node)
    graph.add_node("load_weekly_planner_context", _ensure_weekly_planner_context_node)
    graph.add_node("action_planner", lambda state: action_planner_node(state, llm))
    graph.add_node("queue_executor", lambda state: queue_executor_node(state, llm))
    graph.add_node("action_executor", lambda state: action_executor_node(state, llm))
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
            "action_planner": "load_context",
            "action_executor": "load_context",
            "queue_executor": "queue_executor",
            "weekly_summary": "load_weekly_summary_context",
            "weekly_planner": "load_weekly_planner_context",
            "recommendations": "load_context",
            "progress_tracker": "load_context",
            "research": "load_context",
            "finalize": "finalize",
        },
    )

    # load_weekly_summary_context -> weekly_summary
    graph.add_edge("load_weekly_summary_context", "weekly_summary")
    # load_weekly_planner_context -> weekly_planner
    graph.add_edge("load_weekly_planner_context", "weekly_planner")

    # load_context -> destino real segun route
    graph.add_conditional_edges(
        "load_context",
        _route_after_context_loader,
        {
            "action_planner": "action_planner",
            "action_executor": "action_executor",
            "weekly_summary": "weekly_summary",
            "weekly_planner": "weekly_planner",
            "recommendations": "recommendations",
            "progress_tracker": "progress_tracker",
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
            "action_executor": "load_context",
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
    model: str,
    user_id: str,
    pending_action_intent: dict | None = None,
    session_mutations_json: str = "[]",
    context_json: str | None = None,
    timeout_seconds: int = 25,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    llm = ChatOpenAI(
        model=model,
        timeout=timeout_seconds,
        temperature=1,
        api_key=api_key,
        base_url=base_url,
    )
    app = build_chat_graph(llm)

    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "user_id": user_id,
        "pending_action_intent": pending_action_intent,
        "session_mutations_json": session_mutations_json,
    }
    if context_json is not None:
        state["context_json"] = context_json
    try:
        result = app.invoke(state, config={"recursion_limit": 50})
    except Exception as exc:
        logger.exception("run_graph_chat: fallo en ejecucion del grafo")
        raise RuntimeError("No se pudo ejecutar el flujo de chat.") from exc
    return (result.get("final_response") or "").strip()
