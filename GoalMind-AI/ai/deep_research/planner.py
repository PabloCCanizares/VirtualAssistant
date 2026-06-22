from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage

from ai.deep_research.types import PlanningResult, ResearchTask
from ai.prompts.deep_research_planner_prompt import DEEP_RESEARCH_PLANNER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry

logger = logging.getLogger(__name__)


def _extract_json_payload(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    try:
        payload = json.loads(text[start : end + 1])
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _clean_title(text: str, fallback: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    return value[:120] if value else fallback


def _fallback_tasks(user_query: str, max_tasks: int) -> list[ResearchTask]:
    blueprint = [
        (
            "task-1",
            "Delimitar objetivo y criterios",
            f"Definir el alcance de la investigacion para: {user_query}",
            10,
        ),
        (
            "task-2",
            "Recopilar evidencia de alta calidad",
            "Buscar fuentes fiables, recientes y relevantes para sostener hechos clave.",
            30,
        ),
        (
            "task-3",
            "Contrastar hallazgos y extraer conclusiones",
            "Comparar fuentes, detectar contradicciones y derivar recomendaciones accionables.",
            50,
        ),
    ]
    tasks = []
    for task_id, title, objective, priority in blueprint[: max(1, max_tasks)]:
        tasks.append(ResearchTask(task_id=task_id, title=title, objective=objective, priority=priority))
    return tasks


def _normalize_tasks(raw_tasks: list[Any], max_tasks: int, fallback_query: str) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    for index, item in enumerate(raw_tasks[: max(1, max_tasks)], start=1):
        if not isinstance(item, dict):
            continue
        task_id = (item.get("task_id") or f"task-{index}").strip()[:40]
        title = _clean_title(item.get("title", ""), fallback=f"Tarea {index}")
        objective = _clean_title(item.get("objective", ""), fallback=f"Investigar: {fallback_query}")
        priority_raw = item.get("priority", 50)
        if isinstance(priority_raw, int):
            priority = max(1, min(100, priority_raw))
        else:
            priority = 50
        tasks.append(
            ResearchTask(
                task_id=task_id,
                title=title,
                objective=objective,
                priority=priority,
            )
        )
    return tasks


def create_research_plan(
    *,
    user_query: str,
    llm,
    memory_summary: str,
    context_summary: str,
    max_tasks: int,
) -> PlanningResult:
    messages = [
        SystemMessage(content=DEEP_RESEARCH_PLANNER_PROMPT),
        SystemMessage(content=f"Consulta: {user_query}"),
        SystemMessage(content=f"Resumen de contexto interno: {context_summary or 'sin contexto'}"),
        SystemMessage(content=f"Memoria previa de investigacion: {memory_summary or 'vacía'}"),
        SystemMessage(content=f"Numero maximo de tareas: {max_tasks}"),
    ]

    rationale = "Plan generado con fallback heuristico."
    try:
        raw = invoke_with_retry(llm, messages, retries=1)
        parsed = _extract_json_payload(raw)
        tasks = _normalize_tasks(parsed.get("tasks", []), max_tasks=max_tasks, fallback_query=user_query)
        if tasks:
            rationale = (parsed.get("rationale") or "").strip() or "Plan generado por planner LLM."
            return PlanningResult(tasks=tasks, rationale=rationale)
    except LLMInvokeError:
        logger.exception("create_research_plan: error invocando LLM planner")
    except Exception:
        logger.exception("create_research_plan: fallo inesperado en parser/planner")

    return PlanningResult(tasks=_fallback_tasks(user_query, max_tasks=max_tasks), rationale=rationale)


def refine_research_plan(
    *,
    llm,
    user_query: str,
    memory_summary: str,
    max_new_tasks: int = 2,
) -> PlanningResult:
    messages = [
        SystemMessage(content=DEEP_RESEARCH_PLANNER_PROMPT),
        SystemMessage(content="Modo refinamiento: propone solo tareas nuevas para cubrir huecos de evidencia."),
        SystemMessage(content=f"Consulta original: {user_query}"),
        SystemMessage(content=f"Estado actual: {memory_summary}"),
        SystemMessage(content=f"Numero maximo de tareas nuevas: {max_new_tasks}"),
    ]

    try:
        raw = invoke_with_retry(llm, messages, retries=1)
        parsed = _extract_json_payload(raw)
        tasks = _normalize_tasks(parsed.get("tasks", []), max_tasks=max_new_tasks, fallback_query=user_query)
        if tasks:
            rationale = (parsed.get("rationale") or "").strip() or "Plan refinado por planner LLM."
            return PlanningResult(tasks=tasks, rationale=rationale)
    except LLMInvokeError:
        logger.exception("refine_research_plan: error invocando LLM planner")
    except Exception:
        logger.exception("refine_research_plan: fallo inesperado")

    followup = ResearchTask(
        task_id="task-refine-1",
        title="Cerrar huecos de evidencia",
        objective=(
            "Realizar una busqueda adicional con foco en fuentes primarias y validar posibles "
            "contradicciones detectadas."
        ),
        priority=40,
    )
    return PlanningResult(tasks=[followup], rationale="Refinamiento heuristico por falta de cobertura.")
