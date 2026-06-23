from ai.state import AppState
from services.action_service import (
    CONFIRM_REQUIRED_ACTIONS,
    _build_update_fields,
    _delete_goal_cascade,
    _delete_project_cascade,
    _ensure_user_id,
    _load_context,
    _parse_object_id,
    _resolve_event_id,
    _resolve_goal_id,
    _resolve_project_id,
    _resolve_task_id,
    _result,
    _safe_int,
    execute_action,
)

__all__ = [
    "CONFIRM_REQUIRED_ACTIONS",
    "action_executor_node",
    "_build_update_fields",
    "_delete_goal_cascade",
    "_delete_project_cascade",
    "_ensure_user_id",
    "_load_context",
    "_parse_object_id",
    "_resolve_event_id",
    "_resolve_goal_id",
    "_resolve_project_id",
    "_resolve_task_id",
    "_result",
    "_safe_int",
]


def action_executor_node(state: AppState, _llm) -> AppState:
    return execute_action(state)
