import json
import logging

from langchain_core.messages import SystemMessage

from ai.prompts.supervisor_prompt import (
    DOC_RESOLVER_PROMPT,
    DOC_WRITE_RESOLVER_PROMPT,
    NOTE_RESOLVER_PROMPT,
    PENDING_ACTION_PROMPT,
    SUPERVISOR_PROMPT,
)
from ai.repositories.context_repository import load_user_collections
from ai.services.action_state import clear_pending_action
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {
    "action",
    "weekly_summary",
    "weekly_plan",
    "recommendations",
    "progress",
    "deep_research",
    "research",
    "document",
}


def _classify_pending_action(llm, messages: list, pending_action: dict) -> str:
    """Usa el LLM para determinar si el usuario confirma, cancela u otra cosa."""
    action_name = pending_action.get("action_name", "accion desconocida")
    params = pending_action.get("parameters", {})
    if action_name == "__queue__":
        queue = params.get("queue", [])
        action_summary = f"Cola de {len(queue)} acciones: " + ", ".join(
            a.get("action_name", "?") for a in queue[:5]
        )
    else:
        action_summary = f"{action_name} con parámetros: {json.dumps(params, ensure_ascii=False)}"

    prompt = PENDING_ACTION_PROMPT.replace("{action_summary}", action_summary)
    llm_messages = [SystemMessage(content=prompt)] + list(messages)
    try:
        raw = invoke_with_retry(llm, llm_messages, retries=1)
        parsed = _parse_supervisor_json(raw)
        intent = parsed.get("intent", "other")
        if intent in {"confirm", "cancel", "other"}:
            return intent
    except LLMInvokeError:
        logger.exception("supervisor_node: error clasificando accion pendiente")
    return "other"


def _parse_supervisor_json(text: str) -> dict:
    """Extrae el JSON de la respuesta del LLM supervisor."""
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
            return json.loads(text[start : end + 1])
        except Exception:
            return {}
    return {}



def _extract_docs_from_mutations(session_mutations_json: str) -> list:
    """Extrae docs de session_mutations (action listed/read) como fallback para el resolver."""
    try:
        mutations = json.loads(session_mutations_json)
    except Exception:
        return []
    if not isinstance(mutations, list):
        return []
    seen_ids = set()
    docs = []
    for mut in mutations:
        if mut.get("type") != "document":
            continue
        if mut.get("action") not in ("listed", "read"):
            continue
        doc_id = str(mut.get("id", ""))
        if not doc_id or doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        description = mut.get("description", "")
        project_name = description[len("proyecto: "):] if description.startswith("proyecto: ") else ""
        docs.append({
            "_id": doc_id,
            "original_name": mut.get("name", "sin nombre"),
            "_project_name": project_name,
        })
    return docs


def _build_doc_list_for_resolver(docs: list, context: dict) -> str:
    """Construye una lista legible de documentos para el prompt del resolvedor LLM."""
    projects_by_id = {str(p.get("_id", "")): p for p in context.get("projects", [])}
    lines = []
    for doc in docs:
        doc_id = str(doc.get("_id", ""))
        name = doc.get("original_name") or doc.get("filename") or "sin nombre"
        project_id = str(doc.get("project_id", ""))
        project = projects_by_id.get(project_id, {})
        project_title = project.get("titulo") or doc.get("_project_name") or "sin proyecto"
        # Categorías del proyecto son ObjectIds; usamos los nombres si están en el contexto
        categories = project.get("categorias", [])
        cat_names = []
        for cat in context.get("categories", []):
            if str(cat.get("_id", "")) in [str(c) for c in categories]:
                cat_names.append(cat.get("nombre") or cat.get("name") or "")
        cats_str = ", ".join(c for c in cat_names if c) or "sin categoría"
        lines.append(f"- ID: {doc_id} | Nombre: {name} | Proyecto: {project_title} | Categorías: {cats_str}")
    return "\n".join(lines)


def _resolve_doc_with_llm(llm, messages: list, doc_list_text: str) -> dict:
    """Llama al LLM para resolver qué documento(s) quiere el usuario."""
    prompt = DOC_RESOLVER_PROMPT.replace("{doc_list}", doc_list_text)
    llm_messages = [SystemMessage(content=prompt)] + list(messages)
    try:
        raw = invoke_with_retry(llm, llm_messages, retries=1)
        result = _parse_supervisor_json(raw)
        if result and isinstance(result.get("doc_ids"), list):
            return result
    except LLMInvokeError:
        logger.exception("supervisor_node: error en resolución de documento")
    return {"doc_ids": [], "ambiguous": True, "clarification": ""}


def _build_project_list_for_resolver(projects: list) -> str:
    """Construye lista legible de proyectos para el resolvedor de notas."""
    lines = []
    for p in projects:
        pid = str(p.get("_id", ""))
        title = p.get("titulo") or "sin titulo"
        lines.append(f"- ID: {pid} | Titulo: {title}")
    return "\n".join(lines)


def _resolve_project_with_llm(llm, messages: list, project_list_text: str, prompt_template=None) -> dict:
    """Llama al LLM para resolver a qué proyecto se refiere el usuario."""
    template = prompt_template if prompt_template is not None else NOTE_RESOLVER_PROMPT
    prompt = template.replace("{project_list}", project_list_text)
    llm_messages = [SystemMessage(content=prompt)] + list(messages)
    try:
        raw = invoke_with_retry(llm, llm_messages, retries=1)
        result = _parse_supervisor_json(raw)
        if result and "project_id" in result:
            return result
    except LLMInvokeError:
        logger.exception("supervisor_node: error resolviendo proyecto para notas")
    return {"project_id": None, "ambiguous": True, "clarification": ""}


def supervisor_node(state: AppState, llm) -> AppState:
    """
    Doble fase:
      Fase 1 (Python puro): detectar confirmacion/cancelacion de acciones pendientes.
      Fase 2 (LLM): clasificar la intencion. NO recibe context_json.
    """
    messages = state.get("messages", [])

    # ── Fase 1: Acciones pendientes (LLM) ─────────────────────────
    pending_action = state.get("pending_action_intent")
    if pending_action:
        intent = _classify_pending_action(llm, messages, pending_action)
        is_queue = pending_action.get("action_name") == "__queue__"

        if intent == "confirm":
            clear_pending_action(state.get("user_id"))
            if is_queue:
                queue = pending_action.get("parameters", {}).get("queue", [])
                return {
                    "route": "queue_executor",
                    "action_confirmed": True,
                    "action_queue": queue,
                    "action_results": [],
                    "action_ref_map": {},
                    "current_action_ref_id": None,
                    "action_result_id": None,
                    "action_result_message": None,
                    "pending_action_intent": None,
                }
            return {"route": "action_executor", "action_confirmed": True}

        if intent == "cancel":
            clear_pending_action(state.get("user_id"))
            return {
                "route": "finalize",
                "pending_action_intent": None,
                "action_confirmed": False,
                "final_response": "Accion cancelada.",
            }

        # intent == "other": recordar al usuario que hay una accion pendiente
        msg = (
            "Tienes acciones pendientes de confirmacion. "
            if is_queue
            else "Tienes una accion pendiente. "
        )
        return {
            "route": "finalize",
            "final_response": msg + "Confirma para ejecutarla o cancela para abortar.",
            "pending_action_intent": pending_action,
        }

    # ── Fase 2: Clasificacion LLM (sin context_json) ──────────────
    llm_messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
    ]
    llm_messages.extend(messages)

    try:
        raw = invoke_with_retry(llm, llm_messages, retries=1)
    except LLMInvokeError:
        logger.exception("supervisor_node: error invocando LLM para clasificacion")
        return {"route": "research", "query_type": "research", "use_critic": False}

    parsed = _parse_supervisor_json(raw)
    category = parsed.get("category", "research")
    use_critic = parsed.get("use_critic", False)

    if category not in VALID_CATEGORIES:
        category = "research"

    if not isinstance(use_critic, bool):
        use_critic = False

    # Si es una consulta profunda, research → deep_research. Por defecto = False.
    if state.get("deep_search_requested", False) and category == "research":
        category = "deep_research"

    # ── Fase 3a: Carga selectiva de contexto ──────────────────────
    user_id = state.get("user_id", "")
    context_needed = parsed.get("context_needed", [])
    if not isinstance(context_needed, list):
        context_needed = []
    valid_collections = {"projects", "goals", "tasks", "events", "documents", "categories"}
    context_needed = [c for c in context_needed if c in valid_collections]

    # Si se cargan documents, siempre incluir projects para poder correlacionar project_id
    if "documents" in context_needed and "projects" not in context_needed:
        context_needed.append("projects")

    loaded_context_json = "{}"
    if context_needed:
        try:
            loaded_context_json = load_user_collections(user_id, context_needed)
        except Exception:
            logger.exception("supervisor_node: error cargando colecciones %s", context_needed)

    result = {
        "route": category,
        "query_type": category,
        "use_critic": use_critic,
        "context_json": loaded_context_json,
    }

    # ── Fase 3b: Resolución de documento / proyecto ────────────────
    doc_op = parsed.get("doc_op")

    # Siempre propagar doc_op al state en operaciones de documento
    if category == "document" and doc_op:
        result["doc_op"] = doc_op
        if doc_op == "read":
            result["doc_read_mode"] = parsed.get("doc_read_mode") or "full"
            result["doc_analyze_points"] = parsed.get("doc_analyze_points") or ""

    # Fase 3b-A: Resolver archivo para lectura (comportamiento existente)
    if category == "document" and doc_op == "read":
        context = {}
        try:
            context = json.loads(loaded_context_json)
        except Exception:
            pass

        docs_from_context = context.get("documents", [])
        docs_from_mutations = _extract_docs_from_mutations(
            state.get("session_mutations_json", "[]")
        )
        context_ids = {str(d.get("_id", "")) for d in docs_from_context}
        extra_docs = [d for d in docs_from_mutations if d["_id"] not in context_ids]
        docs = docs_from_context + extra_docs

        if docs:
            doc_list_text = _build_doc_list_for_resolver(docs, context)
            resolution = _resolve_doc_with_llm(llm, messages, doc_list_text)

            if resolution.get("ambiguous"):
                clarification = resolution.get("clarification") or "¿Qué documento deseas consultar?"
                return {
                    **result,
                    "route": "finalize",
                    "use_critic": False,
                    "final_response": clarification,
                }

            doc_ids = resolution.get("doc_ids", [])
            if len(doc_ids) > 1:
                result["doc_target_ids"] = doc_ids
            elif len(doc_ids) == 1:
                result["doc_target_id"] = doc_ids[0]

    # Fase 3b-B: Resolver proyecto para operaciones de notas
    elif category == "document" and doc_op in ("read_notes", "write_note"):
        context = {}
        try:
            context = json.loads(loaded_context_json)
        except Exception:
            pass

        projects = context.get("projects", [])
        if not projects:
            return {
                **result,
                "route": "finalize",
                "use_critic": False,
                "final_response": "No encontré proyectos en tu cuenta. ¿A qué proyecto te refieres?",
            }

        if len(projects) == 1:
            result["doc_target_project_id"] = str(projects[0].get("_id", ""))
        else:
            project_list_text = _build_project_list_for_resolver(projects)
            resolution = _resolve_project_with_llm(llm, messages, project_list_text)
            if resolution.get("ambiguous"):
                clarification = resolution.get("clarification") or "¿A qué proyecto te refieres?"
                return {
                    **result,
                    "route": "finalize",
                    "use_critic": False,
                    "final_response": clarification,
                }
            if resolution.get("project_id"):
                result["doc_target_project_id"] = resolution["project_id"]

    # Fase 3b-C: Resolver proyecto para operaciones de escritura de archivo
    elif category == "document" and doc_op == "write":
        context = {}
        try:
            context = json.loads(loaded_context_json)
        except Exception:
            pass

        projects = context.get("projects", [])
        if projects:
            if len(projects) == 1:
                result["doc_target_project_id"] = str(projects[0].get("_id", ""))
            else:
                project_list_text = _build_project_list_for_resolver(projects)
                resolution = _resolve_project_with_llm(
                    llm, messages, project_list_text, DOC_WRITE_RESOLVER_PROMPT
                )
                if resolution.get("ambiguous"):
                    clarification = resolution.get("clarification") or "¿En qué proyecto quieres crear el documento?"
                    return {
                        **result,
                        "route": "finalize",
                        "use_critic": False,
                        "final_response": clarification,
                    }
                if resolution.get("project_id"):
                    result["doc_target_project_id"] = resolution["project_id"]

    return result


def route_after_supervisor(state: AppState) -> str:
    return state.get("route", "research")
