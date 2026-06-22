from __future__ import annotations

import json
import logging

from langchain_core.messages import SystemMessage

from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.types import DeepResearchRuntimeConfig
from ai.prompts.deep_research_report_prompt import DEEP_RESEARCH_REPORT_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry

logger = logging.getLogger(__name__)


def _fallback_report(memory: DeepResearchMemory, user_query: str, max_sources: int) -> str:
    sources = memory.top_sources(max_sources)
    tasks = memory.to_plan_snapshot()

    lines = [
        "## 1) Resumen ejecutivo",
        f"Investigacion completada para: {user_query}",
        "",
        "## 2) Plan de investigacion ejecutado",
    ]
    if not tasks:
        lines.append("- No se genero un plan estructurado.")
    else:
        for task in tasks:
            lines.append(
                f"- [{task['status']}] {task['title']} (intentos: {task['attempts']}, prioridad: {task['priority']})"
            )

    lines.extend(["", "## 3) Hallazgos principales"])
    if not sources:
        lines.append("- No se obtuvo evidencia suficiente para generar hallazgos concluyentes.")
    else:
        for index, src in enumerate(sources, start=1):
            snippet = (src.get("snippet") or "").strip()
            lines.append(f"- [{index}] {src.get('title')}: {snippet[:180]}")

    lines.extend(["", "## 4) Calidad y limitaciones de evidencia"])
    if memory.warnings:
        for warning in memory.warnings[:5]:
            lines.append(f"- {warning}")
    else:
        lines.append("- No se registraron advertencias criticas durante la ejecucion.")

    if memory.contradictions:
        lines.append("- Posibles contradicciones detectadas:")
        for contradiction in memory.contradictions[:3]:
            lines.append(f"  - {contradiction}")

    lines.extend([
        "",
        "## 5) Conclusiones y recomendaciones accionables",
        "- Validar con una fuente primaria antes de tomar decisiones de alto impacto.",
        "- Priorizar acciones respaldadas por multiples fuentes independientes.",
        "",
        "## 6) Fuentes",
    ])

    if not sources:
        lines.append("- Sin fuentes verificables en esta ejecucion.")
    else:
        for index, src in enumerate(sources, start=1):
            url = src.get("url") or "(sin URL)"
            lines.append(f"- [{index}] {src.get('title')} - {url}")

    return "\n".join(lines).strip()


def generate_research_report(
    *,
    user_query: str,
    memory: DeepResearchMemory,
    llm,
    runtime_config: DeepResearchRuntimeConfig,
) -> str:
    sources = memory.top_sources(runtime_config.max_report_sources)
    payload = {
        "query": user_query,
        "plan": memory.to_plan_snapshot(),
        "iterations": memory.to_iteration_snapshot(),
        "evidence": sources,
        "warnings": memory.warnings,
        "contradictions": memory.contradictions,
    }

    messages = [
        SystemMessage(content=DEEP_RESEARCH_REPORT_PROMPT),
        SystemMessage(content=f"Material de investigacion (JSON): {json.dumps(payload, ensure_ascii=True)}"),
    ]

    try:
        report = invoke_with_retry(llm, messages, retries=1)
        cleaned = (report or "").strip()
        if cleaned:
            return cleaned
    except LLMInvokeError:
        logger.exception("generate_research_report: error invocando LLM report")
    except Exception:
        logger.exception("generate_research_report: fallo inesperado")

    return _fallback_report(memory, user_query=user_query, max_sources=runtime_config.max_report_sources)
