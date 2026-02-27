import json
import logging
from typing import Any, Dict

from langchain_core.messages import SystemMessage

from ai.prompts.intent_interpreter_prompt import INTENT_INTERPRETER_PROMPT
from ai.services.action_state import set_pending_action
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {
    # CRUD existentes
    "create_project",
    "create_goal",
    "create_task",
    "delete_project",
    "delete_goal",
    "delete_task",
    # Nuevas: edicion
    "update_project",
    "update_goal",
    "update_task",
    "mark_task_complete",
    # Nuevas: eventos
    "create_event",
    "delete_event",
}

CONFIRM_REQUIRED_ACTIONS = {"delete_project", "delete_goal", "delete_task", "delete_event"}


def _safe_parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass

    # Intentar extraer el primer bloque JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return {}
    return {}


def _normalize_intent(data: Dict[str, Any]) -> Dict[str, Any]:
    action_name = data.get("action_name")
    confidence = data.get("confidence")
    parameters = data.get("parameters")
    needs_confirmation = data.get("needs_confirmation")
    clarification_question = data.get("clarification_question")

    if not isinstance(action_name, str):
        action_name = None
    else:
        action_name = action_name.strip()
        if action_name not in ALLOWED_ACTIONS:
            action_name = None
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    if not isinstance(parameters, dict):
        parameters = {}
    if not isinstance(needs_confirmation, bool):
        needs_confirmation = False
    if clarification_question is not None and not isinstance(clarification_question, str):
        clarification_question = None

    return {
        "action_name": action_name,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "parameters": parameters,
        "needs_confirmation": needs_confirmation,
        "clarification_question": clarification_question,
    }


def intent_interpreter_node(state: AppState, llm) -> AppState:
    messages = [
        SystemMessage(content=INTENT_INTERPRETER_PROMPT),
        SystemMessage(content=f"Contexto del usuario (JSON): {state.get('context_json', '{}')}"),
    ]
    messages.extend(state.get("messages", []))

    try:
        raw_response = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("intent_interpreter_node: error invocando LLM")
        return {
            "action_name": None,
            "action_confidence": 0.0,
            "action_parameters": {},
            "action_needs_confirmation": False,
            "action_clarification_question": None,
        }

    data = _safe_parse_json(raw_response)
    intent = _normalize_intent(data)

    action_name = intent.get("action_name")
    confidence = intent.get("confidence", 0.0)
    needs_confirmation = intent.get("needs_confirmation", False)
    clarification_question = intent.get("clarification_question")

    if action_name in CONFIRM_REQUIRED_ACTIONS:
        needs_confirmation = True

    result: Dict[str, Any] = {
        "action_name": action_name,
        "action_confidence": confidence,
        "action_parameters": intent.get("parameters", {}),
        "action_needs_confirmation": needs_confirmation,
        "action_clarification_question": clarification_question,
    }

    if clarification_question:
        result["draft_response"] = clarification_question
        return result

    if action_name and needs_confirmation:
        user_id = state.get("user_id")
        pending = {
            "action_name": action_name,
            "parameters": intent.get("parameters", {}),
        }
        set_pending_action(user_id, pending)
        result["pending_action_intent"] = pending
        result["action_confirmed"] = False
        result[
            "draft_response"
        ] = "¿Confirmas esta accion? Responde 'confirmo' para continuar o 'cancela' para abortar."
        return result

    return result
