"""Relationship map for GoalMind AI operating context."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.heuristics.types import bounded_limit
from services.user_context_service import (
    DOCUMENT_FIELDS,
    GOAL_FIELDS,
    PROJECT_FIELDS,
    TASK_FIELDS,
    doc_id,
    get_user_dataset,
    is_completed,
    public_doc,
    ref_id,
    serialize_value,
)

EVENT_FIELDS = (
    "_id",
    "titulo",
    "title",
    "descripcion",
    "tipo_evento",
    "fecha_inicio",
    "fecha_fin",
    "id_tarea",
    "id_objetivo",
    "usuario_id",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _label(item: dict, *fields: str, fallback: str = "Sin titulo") -> str:
    for field in fields:
        value = _clean(item.get(field))
        if value:
            return value
    return fallback


def _task_goal_id(task: dict) -> str:
    return ref_id(task.get("objetivo_id") or task.get("goal_id"))


def _task_project_id(task: dict) -> str:
    return ref_id(task.get("project_id"))


def _event_task_id(event: dict) -> str:
    return ref_id(event.get("id_tarea") or event.get("task_id"))


def _event_goal_id(event: dict) -> str:
    return ref_id(event.get("id_objetivo") or event.get("goal_id"))


def _node_id(kind: str, entity_id: str) -> str:
    return f"{kind}:{entity_id}"


def _add_edge(edges: list[dict[str, Any]], source: str, target: str, relation: str) -> None:
    if not source or not target:
        return
    edges.append({"source": source, "target": target, "relation": relation})


def _make_node(kind: str, item: dict, label: str, fields: tuple[str, ...]) -> dict[str, Any]:
    entity_id = doc_id(item)
    return {
        "id": _node_id(kind, entity_id),
        "type": kind,
        "entity_id": entity_id,
        "label": label,
        "data": public_doc(item, fields),
    }


def _index_by_id(items: list[dict]) -> dict[str, dict]:
    return {doc_id(item): item for item in items}


def _project_summaries(dataset: dict, edges: list[dict], *, limit: int) -> list[dict]:
    goals_by_project: dict[str, list[dict]] = {}
    tasks_by_goal: dict[str, list[dict]] = {}
    tasks_by_project: dict[str, list[dict]] = {}
    documents_by_project: dict[str, list[dict]] = {}
    events_by_goal: dict[str, list[dict]] = {}
    events_by_task: dict[str, list[dict]] = {}

    for goal in dataset["goals"]:
        goals_by_project.setdefault(ref_id(goal.get("project_id")), []).append(goal)
    for task in dataset["tasks"]:
        goal_id = _task_goal_id(task)
        project_id = _task_project_id(task)
        if goal_id:
            tasks_by_goal.setdefault(goal_id, []).append(task)
        if project_id:
            tasks_by_project.setdefault(project_id, []).append(task)
    for document in dataset["documents"]:
        documents_by_project.setdefault(ref_id(document.get("project_id")), []).append(document)
    for event in dataset["events"]:
        task_id = _event_task_id(event)
        goal_id = _event_goal_id(event)
        if task_id:
            events_by_task.setdefault(task_id, []).append(event)
        if goal_id:
            events_by_goal.setdefault(goal_id, []).append(event)

    edge_counts: dict[str, int] = {}
    for edge in edges:
        edge_counts[edge["source"]] = edge_counts.get(edge["source"], 0) + 1
        edge_counts[edge["target"]] = edge_counts.get(edge["target"], 0) + 1

    summaries = []
    for project in dataset["projects"]:
        project_id = doc_id(project)
        goals = goals_by_project.get(project_id, [])
        goal_ids = {doc_id(goal) for goal in goals}
        goal_tasks = [task for goal_id in goal_ids for task in tasks_by_goal.get(goal_id, [])]
        project_tasks = tasks_by_project.get(project_id, [])
        task_ids = {doc_id(task) for task in goal_tasks + project_tasks}
        event_count = sum(len(events_by_goal.get(goal_id, [])) for goal_id in goal_ids)
        event_count += sum(len(events_by_task.get(task_id, [])) for task_id in task_ids)
        pending = [task for task in goal_tasks + project_tasks if not is_completed(task)]
        summaries.append(
            {
                "project": public_doc(project, PROJECT_FIELDS),
                "counts": {
                    "goals": len(goals),
                    "tasks": len(goal_tasks) + len(project_tasks),
                    "pending_tasks": len(pending),
                    "documents": len(documents_by_project.get(project_id, [])),
                    "notes": len(project.get("notas") or []),
                    "events": event_count,
                    "degree": edge_counts.get(_node_id("project", project_id), 0),
                },
            }
        )
    summaries.sort(
        key=lambda item: (
            -item["counts"]["pending_tasks"],
            -item["counts"]["degree"],
            _clean((item["project"] or {}).get("titulo")).lower(),
        )
    )
    return summaries[:limit]


def _disconnected_entities(dataset: dict) -> dict[str, list[dict]]:
    project_ids = {doc_id(project) for project in dataset["projects"]}
    goal_ids = {doc_id(goal) for goal in dataset["goals"]}
    task_ids = {doc_id(task) for task in dataset["tasks"]}

    tasks_without_parent = []
    tasks_missing_parent = []
    for task in dataset["tasks"]:
        goal_id = _task_goal_id(task)
        project_id = _task_project_id(task)
        if not goal_id and not project_id:
            tasks_without_parent.append(public_doc(task, TASK_FIELDS))
        elif (goal_id and goal_id not in goal_ids) or (
            project_id and project_id not in project_ids
        ):
            tasks_missing_parent.append(public_doc(task, TASK_FIELDS))

    documents_without_project = [
        public_doc(document, DOCUMENT_FIELDS)
        for document in dataset["documents"]
        if not ref_id(document.get("project_id"))
        or ref_id(document.get("project_id")) not in project_ids
    ]
    events_without_link = [
        public_doc(event, EVENT_FIELDS)
        for event in dataset["events"]
        if not _event_task_id(event) and not _event_goal_id(event)
    ]
    events_missing_link = [
        public_doc(event, EVENT_FIELDS)
        for event in dataset["events"]
        if (_event_task_id(event) and _event_task_id(event) not in task_ids)
        or (_event_goal_id(event) and _event_goal_id(event) not in goal_ids)
    ]

    return {
        "tasks_without_parent": tasks_without_parent,
        "tasks_missing_parent": tasks_missing_parent,
        "documents_without_project": documents_without_project,
        "events_without_link": events_without_link,
        "events_missing_link": events_missing_link,
    }


def _top_connected_nodes(nodes: list[dict], edges: list[dict], *, limit: int) -> list[dict]:
    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    node_by_id = {node["id"]: node for node in nodes}
    ranked = [
        {
            "id": node_id,
            "type": node_by_id[node_id]["type"],
            "entity_id": node_by_id[node_id]["entity_id"],
            "label": node_by_id[node_id]["label"],
            "degree": count,
        }
        for node_id, count in degree.items()
        if node_id in node_by_id
    ]
    ranked.sort(key=lambda item: (-item["degree"], item["type"], item["label"]))
    return ranked[:limit]


def build_operating_map(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int | str | None = 50,
    include_events: bool = True,
) -> dict[str, Any]:
    """Build a read-only relationship map across projects, goals and work items."""
    current = now or datetime.utcnow()
    bounded = bounded_limit(limit, default=50, maximum=200)
    dataset = get_user_dataset(usuario_id=usuario_id)
    projects_by_id = _index_by_id(dataset["projects"])
    goals_by_id = _index_by_id(dataset["goals"])
    tasks_by_id = _index_by_id(dataset["tasks"])

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for project in dataset["projects"]:
        nodes.append(_make_node("project", project, _label(project, "titulo"), PROJECT_FIELDS))
    for goal in dataset["goals"]:
        goal_id = doc_id(goal)
        project_id = ref_id(goal.get("project_id"))
        nodes.append(_make_node("goal", goal, _label(goal, "titulo"), GOAL_FIELDS))
        if project_id in projects_by_id:
            _add_edge(edges, _node_id("project", project_id), _node_id("goal", goal_id), "has_goal")
    for task in dataset["tasks"]:
        task_id = doc_id(task)
        goal_id = _task_goal_id(task)
        project_id = _task_project_id(task)
        nodes.append(_make_node("task", task, _label(task, "contenido", "titulo"), TASK_FIELDS))
        if goal_id in goals_by_id:
            _add_edge(edges, _node_id("goal", goal_id), _node_id("task", task_id), "has_task")
        elif project_id in projects_by_id:
            _add_edge(
                edges,
                _node_id("project", project_id),
                _node_id("task", task_id),
                "has_unscoped_task",
            )
    for document in dataset["documents"]:
        document_id = doc_id(document)
        project_id = ref_id(document.get("project_id"))
        goal_id = ref_id(document.get("goal_id"))
        nodes.append(
            _make_node(
                "document",
                document,
                _label(document, "original_name", "filename"),
                DOCUMENT_FIELDS,
            )
        )
        if project_id in projects_by_id:
            _add_edge(
                edges,
                _node_id("project", project_id),
                _node_id("document", document_id),
                "has_document",
            )
        if goal_id in goals_by_id:
            _add_edge(
                edges,
                _node_id("goal", goal_id),
                _node_id("document", document_id),
                "supports_goal",
            )
    if include_events:
        for event in dataset["events"]:
            event_id = doc_id(event)
            task_id = _event_task_id(event)
            goal_id = _event_goal_id(event)
            nodes.append(
                _make_node(
                    "event",
                    event,
                    _label(event, "titulo", "title", "descripcion", fallback="Evento"),
                    EVENT_FIELDS,
                )
            )
            if task_id in tasks_by_id:
                _add_edge(
                    edges, _node_id("task", task_id), _node_id("event", event_id), "scheduled_event"
                )
            if goal_id in goals_by_id:
                _add_edge(
                    edges, _node_id("goal", goal_id), _node_id("event", event_id), "goal_event"
                )

    returned_nodes = nodes[:bounded]
    returned_node_ids = {node["id"] for node in returned_nodes}
    returned_edges = [
        edge
        for edge in edges
        if edge["source"] in returned_node_ids and edge["target"] in returned_node_ids
    ][: bounded * 3]

    return serialize_value(
        {
            "user_id": dataset["user_id"],
            "generated_at": current,
            "summary": {
                "nodes_total": len(nodes),
                "edges_total": len(edges),
                "nodes_returned": len(returned_nodes),
                "edges_returned": len(returned_edges),
                "include_events": include_events,
            },
            "nodes": returned_nodes,
            "edges": returned_edges,
            "project_summaries": _project_summaries(dataset, edges, limit=min(bounded, 25)),
            "top_connected_nodes": _top_connected_nodes(nodes, edges, limit=min(bounded, 25)),
            "disconnected_entities": _disconnected_entities(dataset),
        }
    )
