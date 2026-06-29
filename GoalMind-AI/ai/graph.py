import logging
from typing import Any, Iterable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover
    ChatGoogleGenerativeAI = None

try:
    from langchain_groq import ChatGroq
except Exception:  # pragma: no cover
    ChatGroq = None

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
from ai.agents.deep_research import deep_research_node
from ai.agents.doc_organizer import doc_organizer_node
from ai.agents.doc_reader import doc_reader_node
from ai.agents.doc_writer import doc_writer_node
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
        "deep_research": "deep_research",
        "research": "research",
        "document": "doc_organizer",
        "off_topic": "finalize",
        "finalize": "finalize",
    }
    return route_map.get(route, "research")


def _route_after_intent(state: AppState) -> str:
    """
    Compatibilidad con el routing de intención anterior.
    Las acciones ambiguas o pendientes de confirmación se finalizan con respuesta al usuario.
    """
    if state.get("action_clarification_question"):
        return "finalize"

    if not state.get("action_name"):
        return "finalize"

    try:
        confidence = float(state.get("action_confidence") or 0)
    except Exception:
        confidence = 0

    if confidence < 0.7:
        return "finalize"

    if state.get("action_needs_confirmation"):
        return "finalize"

    return "action_executor"


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
    if state.get("final_response") and not state.get("action_queue"):
        return "finalize"
    if state.get("action_name"):
        return "action_executor"
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
        "deep_research": "deep_research",
        "research": "research",
        "document": "doc_organizer",
    }
    return route_map.get(route, "research")


def _route_after_doc_organizer(state: AppState) -> str:
    if state.get("doc_error"):
        return "finalize"
    if state.get("doc_op") in {"write", "write_note"}:
        return "doc_writer"
    return "doc_reader"


def _route_after_deep_research(state: AppState) -> str:
    if state.get("deep_search_error"):
        return "research"
    if (state.get("deep_research_notes") or "").strip():
        return "writer"
    if (state.get("research_notes") or "").strip():
        return "writer"
    return "research"


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
    deep_error = (state.get("deep_search_error") or "").strip()
    if deep_error and state.get("deep_search_mode") == "on":
        logger.warning("Deep search no disponible: %s", deep_error)

    final_response = (state.get("final_response") or "").strip()
    if final_response:
        return {"final_response": final_response}

    draft = (state.get("draft_response") or "").strip()
    if not draft:
        draft = "No pude generar una respuesta en este momento."
    return {"final_response": draft}


def _build_llm(provider: str, model: str, api_key: str | None, timeout_seconds: int):
    provider_name = (provider or "").strip().lower()

    if provider_name == "openai":
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            timeout=timeout_seconds,
            temperature=1,
        )

    if provider_name == "gemini":
        if ChatGoogleGenerativeAI is None:
            raise RuntimeError(
                "Proveedor Gemini no disponible. Instala 'langchain-google-genai'."
            )
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
        )

    if provider_name == "groq":
        if ChatGroq is None:
            raise RuntimeError(
                "Proveedor Groq no disponible. Instala 'langchain-groq'."
            )
        return ChatGroq(
            model=model,
            api_key=api_key,
        )

    raise ValueError(f"Proveedor de modelo no soportado: '{provider}'.")


def build_llm(provider: str, model: str, api_key: str | None, timeout_seconds: int):
    return _build_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


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
    graph.add_node("deep_research", lambda state: deep_research_node(state, llm))
    graph.add_node("research", lambda state: research_node(state, llm))
    graph.add_node("recommendations", lambda state: recommendations_node(state, llm))
    graph.add_node("weekly_summary", lambda state: weekly_summary_node(state, llm))
    graph.add_node("weekly_planner", lambda state: weekly_planner_node(state, llm))
    graph.add_node("progress_tracker", lambda state: progress_tracker_node(state, llm))
    graph.add_node("doc_organizer", doc_organizer_node)
    graph.add_node("doc_reader", lambda state: doc_reader_node(state, llm))
    graph.add_node("doc_writer", lambda state: doc_writer_node(state, llm))
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
            "deep_research": "load_context",
            "research": "load_context",
            "doc_organizer": "load_context",
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
            "deep_research": "deep_research",
            "research": "research",
            "doc_organizer": "doc_organizer",
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

    # deep_research → writer si produjo notas; si falla, research interno
    graph.add_conditional_edges(
        "deep_research",
        _route_after_deep_research,
        {"writer": "writer", "research": "research"},
    )

    # doc_organizer → lector/escritor/finalize
    graph.add_conditional_edges(
        "doc_organizer",
        _route_after_doc_organizer,
        {
            "doc_reader": "doc_reader",
            "doc_writer": "doc_writer",
            "finalize": "finalize",
        },
    )
    graph.add_edge("doc_reader", "finalize")
    graph.add_edge("doc_writer", "finalize")

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
    provider: str = "openai",
    api_key: str | None = None,
    pending_action_intent: dict | None = None,
    session_mutations_json: str = "[]",
    context_json: str | None = None,
    timeout_seconds: int = 25,
    deep_search_mode: str = "auto",
    deep_search_requested: bool = False,
    deep_search_error: str = "",
) -> str:
    try:
        llm = build_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except TypeError:
        llm = build_llm(model=model)
    app = build_chat_graph(llm)

    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "user_id": user_id,
        "pending_action_intent": pending_action_intent,
        "session_mutations_json": session_mutations_json,
        "deep_search_mode": deep_search_mode,
        "deep_search_requested": deep_search_requested,
        "deep_search_error": deep_search_error,
    }
    if context_json is not None:
        state["context_json"] = context_json
    try:
        result = app.invoke(state, config={"recursion_limit": 50})
    except Exception as exc:
        logger.exception("run_graph_chat: fallo en ejecucion del grafo")
        raise RuntimeError("No se pudo ejecutar el flujo de chat.") from exc
    return (result.get("final_response") or "").strip()
