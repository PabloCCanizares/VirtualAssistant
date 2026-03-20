from typing import Any, TypedDict

from langchain_core.messages import BaseMessage


class ActionIntent(TypedDict, total=False):
    action_name: str
    parameters: dict[str, Any]


class AppState(TypedDict, total=False):
    messages: list[BaseMessage]
    context_json: str
    user_id: str
    deep_search_mode: str  # auto|on|off (modo solicitado para deep search)
    deep_search_requested: bool  # flag computado para fases futuras de routing
    deep_search_error: str  # motivo si deep search no puede activarse
    deep_search_results: list[dict[str, Any]]  # resultados crudos de proveedor de búsqueda
    deep_research_notes: str  # notas/sintesis de investigación profunda
    deep_research_sources: list[dict[str, Any]]  # fuentes normalizadas con URL/título/snippet
    deep_research_plan: list[dict[str, Any]]  # plan de investigacion generado por planner
    deep_research_iterations: list[dict[str, Any]]  # trazas de cada iteracion ejecutada
    deep_research_warnings: list[str]  # advertencias no fatales durante la investigacion
    route: str
    use_critic: bool
    fallback_route: str  # deprecated: mantenido por compatibilidad
    query_type: str  # categoria detectada por el supervisor LLM
    research_notes: str
    progress_analysis: str  # output del progress_tracker (consume el writer)
    weekly_plan: str  # output del weekly_planner (va directo a finalize)
    draft_response: str
    final_response: str
    action_name: str
    action_confidence: float
    action_parameters: dict[str, Any]
    action_needs_confirmation: bool
    action_clarification_question: str
    pending_action_intent: ActionIntent
    action_confirmed: bool
    # --- Cola de acciones múltiples ---
    action_queue: list[dict]        # acciones pendientes de ejecutar en la cola
    action_results: list[dict]      # resultados acumulados de cada acción ejecutada
    action_ref_map: dict[str, str]  # {ref_id → id_real} para resolver dependencias
    current_action_ref_id: str      # ref_id de la acción que se está ejecutando ahora
    action_result_id: str           # ID del documento creado/afectado por action_executor
    action_result_message: str      # mensaje resultado de action_executor (para la cola)
    # --- Contexto de mutaciones de sesión ---
    session_mutations_json: str     # JSON string de las mutaciones de esta sesión
    # --- Operaciones sobre documentos ---
    doc_op: str                    # "read" | "write"
    doc_read_mode: str             # "full" | "summary" | "analyze"
    doc_target_id: str             # _id del documento (para lectura)
    doc_target_name: str           # original_name del documento
    doc_target_project_id: str     # project_id resuelto
    doc_target_goal_id: str        # goal_id resuelto (opcional)
    doc_content_text: str          # texto extraído del documento
    doc_analyze_points: str        # puntos concretos a analizar
    doc_write_format: str          # "txt" | "pdf"
    doc_write_filename: str        # nombre del archivo generado
    doc_error: str                 # error si algo falla en rama document
