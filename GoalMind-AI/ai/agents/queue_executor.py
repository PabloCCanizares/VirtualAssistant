import logging
import re
from typing import Any, Dict, List, Optional

from ai.state import AppState

logger = logging.getLogger(__name__)


def _resolve_refs(params: Dict[str, Any], ref_map: Dict[str, str]) -> Dict[str, Any]:
    """Sustituye valores '$ref:alias' por el ID real almacenado en ref_map."""
    if not ref_map:
        return params
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str):
            match = re.fullmatch(r"\$ref:(\w+)", value.strip())
            if match:
                alias = match.group(1)
                resolved[key] = ref_map.get(alias, value)
                continue
        resolved[key] = value
    return resolved


def _build_summary(results: List[Dict[str, Any]]) -> str:
    messages = [r["message"] for r in results if r.get("message")]
    if not messages:
        return "No se ejecutaron acciones."
    if len(messages) == 1:
        return messages[0]
    lines = "\n".join(f"- {m}" for m in messages)
    return f"Acciones completadas:\n{lines}"


def queue_executor_node(state: AppState, _llm) -> AppState:
    queue: List[Dict] = list(state.get("action_queue") or [])
    results: List[Dict] = list(state.get("action_results") or [])
    ref_map: Dict[str, str] = dict(state.get("action_ref_map") or {})

    # Recoger resultado de action_executor si venimos de el
    prev_message: Optional[str] = state.get("action_result_message")
    if prev_message is not None:
        prev_id: Optional[str] = state.get("action_result_id")
        prev_ref_id: Optional[str] = state.get("current_action_ref_id")
        results.append({
            "ref_id": prev_ref_id,
            "id": prev_id,
            "message": prev_message,
        })
        if prev_ref_id and prev_id:
            ref_map[prev_ref_id] = prev_id

    base_updates: Dict[str, Any] = {
        "action_results": results,
        "action_ref_map": ref_map,
        "action_result_message": None,
        "action_result_id": None,
        "current_action_ref_id": None,
    }

    if not queue:
        # Cola vacia: construir resumen final
        base_updates["final_response"] = _build_summary(results)
        base_updates["action_queue"] = []
        return base_updates

    # Sacar la siguiente accion
    current = queue.pop(0)
    resolved_params = _resolve_refs(current.get("action_parameters", {}), ref_map)

    base_updates.update({
        "route": "action_executor",
        "action_name": current["action_name"],
        "action_parameters": resolved_params,
        "current_action_ref_id": current.get("ref_id"),
        "action_queue": queue,
        "action_confirmed": True,   # la cola fue pre-confirmada por action_planner o supervisor
        "action_needs_confirmation": False,
    })
    return base_updates
