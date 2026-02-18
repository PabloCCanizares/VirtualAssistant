import logging
from typing import Any, Iterable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents import (
    action_executor_node,
    critic_node,
    intent_interpreter_node,
    recommendations_node,
    research_node,
    route_after_supervisor,
    supervisor_node,
    weekly_summary_node,
    writer_node,
)
from state import AppState

logger = logging.getLogger(__name__)
VALID_FALLBACK_ROUTES = {"research", "recommendations", "weekly_summary", "writer"}


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


def _route_after_writer(state: AppState) -> str:
    return "critic" if state.get("use_critic", False) else "finalize"


def _finalize_node(state: AppState) -> AppState:
    final_response = (state.get("final_response") or "").strip()
    if final_response:
        return {"final_response": final_response}

    draft = (state.get("draft_response") or "").strip()
    if not draft:
        draft = "No pude generar una respuesta en este momento."
    return {"final_response": draft}


def _route_after_intent(state: AppState) -> str:
    action_name = state.get("action_name")
    confidence = state.get("action_confidence", 0.0) or 0.0
    needs_confirmation = state.get("action_needs_confirmation", False)
    clarification = state.get("action_clarification_question")
    fallback = state.get("fallback_route", "research")
    if fallback not in VALID_FALLBACK_ROUTES:
        fallback = "research"

    if clarification:
        return "finalize"

    if not action_name or confidence < 0.6:
        return fallback

    if action_name == "weekly_summary":
        return "weekly_summary"

    if needs_confirmation:
        return "finalize"

    return "action_executor"


def build_chat_graph(llm):
    graph = StateGraph(AppState)

    graph.add_node("supervisor", lambda state: supervisor_node(state, llm))
    graph.add_node("intent_interpreter", lambda state: intent_interpreter_node(state, llm))
    graph.add_node("action_executor", lambda state: action_executor_node(state, llm))
    graph.add_node("research", lambda state: research_node(state, llm))
    graph.add_node("recommendations", lambda state: recommendations_node(state, llm))
    graph.add_node("weekly_summary", lambda state: weekly_summary_node(state, llm))
    graph.add_node("writer", lambda state: writer_node(state, llm))
    graph.add_node("critic", lambda state: critic_node(state, llm))
    graph.add_node("finalize", _finalize_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "intent_interpreter": "intent_interpreter",
            "action_executor": "action_executor",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "intent_interpreter",
        _route_after_intent,
        {
            "action_executor": "action_executor",
            "finalize": "finalize",
            "research": "research",
            "recommendations": "recommendations",
            "weekly_summary": "weekly_summary",
            "writer": "writer",
        },
    )
    graph.add_edge("research", "writer")
    graph.add_conditional_edges(
        "recommendations",
        _route_after_writer,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "weekly_summary",
        _route_after_writer,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "writer",
        _route_after_writer,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )
    graph.add_edge("action_executor", "finalize")
    graph.add_edge("critic", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_graph_chat(
    user_message: str,
    history,
    context_json: str,
    model: str,
    user_id: str,
    pending_action_intent: dict | None = None,
) -> str:
    llm = ChatOpenAI(model=model, timeout=45)
    app = build_chat_graph(llm)

    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "context_json": context_json or "{}",
        "user_id": user_id,
        "pending_action_intent": pending_action_intent,
    }
    try:
        result = app.invoke(state, config={"recursion_limit": 25})
    except Exception as exc:
        logger.exception("run_graph_chat: fallo en ejecucion del grafo")
        raise RuntimeError("No se pudo ejecutar el flujo de chat.") from exc
    return (result.get("final_response") or "").strip()
