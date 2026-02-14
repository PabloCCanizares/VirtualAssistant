from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents import critic_node, research_node, route_after_supervisor, supervisor_node, writer_node
from state import AppState


def _history_to_messages(history) -> list:
    messages = []
    for item in history or []:
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


def build_chat_graph(llm):
    graph = StateGraph(AppState)

    graph.add_node("supervisor", lambda state: supervisor_node(state, llm))
    graph.add_node("research", lambda state: research_node(state, llm))
    graph.add_node("writer", lambda state: writer_node(state, llm))
    graph.add_node("critic", lambda state: critic_node(state, llm))
    graph.add_node("finalize", _finalize_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "research": "research",
            "writer": "writer",
        },
    )
    graph.add_edge("research", "writer")
    graph.add_conditional_edges(
        "writer",
        _route_after_writer,
        {
            "critic": "critic",
            "finalize": "finalize",
        },
    )
    graph.add_edge("critic", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_graph_chat(user_message: str, history, context_json: str, model: str) -> str:
    llm = ChatOpenAI(model=model, temperature=0.3)
    app = build_chat_graph(llm)

    state = {
        "messages": _history_to_messages(history) + [HumanMessage(content=user_message)],
        "context_json": context_json,
    }
    result = app.invoke(state)
    return (result.get("final_response") or "").strip()
