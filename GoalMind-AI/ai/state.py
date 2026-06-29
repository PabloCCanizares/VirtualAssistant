from typing import Any, TypedDict

from langchain_core.messages import BaseMessage


class ActionIntent(TypedDict, total=False):
    action_name: str
    parameters: dict[str, Any]


class AppState(TypedDict, total=False):
    messages: list[BaseMessage]
    context_json: str
    user_id: str
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
    # --- Deep search / deep research ---
    deep_search_mode: str
    deep_search_requested: bool
    deep_search_error: str
    deep_search_results: list[dict]
    deep_research_sources: list[dict]
    deep_research_notes: str
    deep_research_plan: list[dict]
    deep_research_iterations: list[dict]
    deep_research_warnings: list[str]
    # --- Documentos ---
    doc_op: str
    doc_error: str
    doc_read_mode: str
    doc_target_id: str
    doc_target_ids: list[str]
    doc_target_name: str
    doc_target_project_id: str
    doc_target_goal_id: str
    doc_content_text: str
    doc_analyze_points: str
    doc_notes_data: list[dict]
