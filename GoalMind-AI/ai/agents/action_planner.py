import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage

from ai.prompts.action_planner_prompt import ACTION_PLANNER_PROMPT
from ai.services.action_state import set_pending_action
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {
    "create_project", "create_goal", "create_task",
    "delete_project", "delete_goal", "delete_task", "delete_event",
    "update_project", "update_goal", "update_task",
    "mark_task_complete", "create_event",
}

CONFIRM_REQUIRED_ACTIONS = {"delete_project", "delete_goal", "delete_task", "delete_event"}


def _safe_parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except Exception:
            return {}
    return {}


def _validate_action(item: Any) -> Dict[str, Any] | None:
    """Valida y normaliza una accion de la lista. Devuelve None si no es valida."""
    if not isinstance(item, dict):
        return None
    action_name = item.get("action_name")
    if not isinstance(action_name, str) or action_name.strip() not in ALLOWED_ACTIONS:
        return None
    params = item.get("action_parameters")
    if not isinstance(params, dict):
        params = {}
    ref_id = item.get("ref_id")
    if not isinstance(ref_id, str) or not ref_id.strip():
        ref_id = None
    return {
        "action_name": action_name.strip(),
        "action_parameters": params,
        "ref_id": ref_id,
    }


def _needs_confirmation(actions: List[Dict[str, Any]]) -> bool:
    return any(a["action_name"] in CONFIRM_REQUIRED_ACTIONS for a in actions)


def action_planner_node(state: AppState, llm) -> AppState:
    print("\n" + "="*60)
    print("ACTION_PLANNER_NODE: Descomponiendo acciones...")
    print("="*60)
    session_mutations = (state.get("session_mutations_json") or "[]").strip()
    context_json = state.get("context_json") or "{}"
    print(f"   Mutaciones de sesion: {len(eval(session_mutations)) if session_mutations != '[]' else 0} registros")
    print(f"   Llamando LLM para analizar acciones...")

    system_parts = [ACTION_PLANNER_PROMPT]
    system_parts.append(f"Contexto del usuario (JSON): {context_json}")
    if session_mutations and session_mutations != "[]":
        system_parts.append(
            f"Operaciones recientes de esta sesion (IDs disponibles para referenciar): "
            f"{session_mutations}"
        )

    messages = [SystemMessage(content="\n\n".join(system_parts))]
    messages.extend(state.get("messages", []))

    try:
        raw = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("action_planner_node: error invocando LLM")
        return {"final_response": "No pude planificar las acciones en este momento."}

    parsed = _safe_parse_json(raw)

    clarification = parsed.get("clarification_question")
    if clarification and isinstance(clarification, str) and clarification.strip():
        return {"draft_response": clarification.strip()}

    raw_actions = parsed.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        return {
            "final_response": "No he podido identificar ninguna accion en tu mensaje. ¿Puedes reformularlo?"
        }

    actions = [_validate_action(item) for item in raw_actions]
    actions = [a for a in actions if a is not None]
    if not actions:
        print(f"   ✗ No se detectaron acciones validas")
        print("="*60 + "\n")
        return {
            "final_response": "Las acciones detectadas no son validas. ¿Puedes reformular tu peticion?"
        }

    print(f"   ✓ {len(actions)} accion(es) detectada(s):")
    for i, act in enumerate(actions, 1):
        print(f"      {i}. {act['action_name']} (ref_id={act.get('ref_id')})")

    if _needs_confirmation(actions):
        user_id = state.get("user_id")
        pending = {
            "action_name": "__queue__",
            "parameters": {"queue": actions},
        }
        set_pending_action(user_id, pending)
        action_names = ", ".join(a["action_name"] for a in actions)
        print(f"   ⚠️  Hay acciones destructivas → pidiendo confirmacion")
        print("="*60 + "\n")
        return {
            "pending_action_intent": pending,
            "action_confirmed": False,
            "draft_response": (
                f"Voy a ejecutar las siguientes acciones: {action_names}. "
                "Alguna de ellas es destructiva. ¿Confirmas? Responde 'confirmo' o 'cancela'."
            ),
        }

    print(f"   → Enrutando a cola para ejecucion...")
    print("="*60 + "\n")
    return {
        "action_queue": actions,
        "action_results": [],
        "action_ref_map": {},
        "current_action_ref_id": None,
        "action_result_id": None,
        "action_result_message": None,
    }
