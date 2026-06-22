from __future__ import annotations

import logging

from ai.config import DeepSearchConfig
from ai.deep_research.analyzer import evaluate_research_step
from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.planner import create_research_plan, refine_research_plan
from ai.deep_research.reporter import generate_research_report
from ai.deep_research.researcher import run_research_step
from ai.deep_research.types import (
    DeepResearchResult,
    DeepResearchRuntimeConfig,
    ResearchIteration,
)

logger = logging.getLogger(__name__)


def _maybe_refine_plan(
    *,
    llm,
    memory: DeepResearchMemory,
    runtime_config: DeepResearchRuntimeConfig,
) -> None:
    if len(memory.tasks) >= runtime_config.max_tasks:
        return
    remaining_capacity = runtime_config.max_tasks - len(memory.tasks)
    if remaining_capacity <= 0:
        return

    refinement = refine_research_plan(
        llm=llm,
        user_query=memory.user_query,
        memory_summary=memory.planner_summary(max_sources=4),
        max_new_tasks=min(2, remaining_capacity),
    )

    existing_ids = {task.task_id for task in memory.tasks}
    new_tasks = [task for task in refinement.tasks if task.task_id not in existing_ids]
    if not new_tasks:
        return

    memory.add_tasks(new_tasks)
    memory.add_warning(f"Plan refinado: {refinement.rationale}")


def run_deep_research(
    *,
    user_query: str,
    context_json: str,
    llm,
    search_config: DeepSearchConfig,
    runtime_config: DeepResearchRuntimeConfig,
    web_search_tool,
) -> DeepResearchResult:
    memory = DeepResearchMemory(user_query=user_query, context_json=context_json or "{}")

    planning = create_research_plan(
        user_query=user_query,
        llm=llm,
        memory_summary=memory.planner_summary(max_sources=3),
        context_summary=memory.context_summary(),
        max_tasks=runtime_config.max_tasks,
    )
    memory.add_tasks(planning.tasks)
    if planning.rationale:
        memory.add_warning(f"Planner: {planning.rationale}")

    for iteration in range(1, runtime_config.max_iterations + 1):
        task = memory.get_next_task()
        if not task:
            break

        task.status = "in_progress"
        task.attempts += 1

        evidence_batch, accepted_queries, step_warnings = run_research_step(
            task=task,
            memory=memory,
            llm=llm,
            search_config=search_config,
            runtime_config=runtime_config,
            web_search_tool=web_search_tool,
        )
        for warning in step_warnings:
            memory.add_warning(warning)

        added_evidence = memory.add_evidence(evidence_batch)
        analysis = evaluate_research_step(
            task=task,
            evidence_batch=added_evidence,
            accepted_queries=accepted_queries,
            memory=memory,
            runtime_config=runtime_config,
        )

        lead_query = accepted_queries[0] if accepted_queries else ""
        memory.add_iteration(
            ResearchIteration(
                iteration=iteration,
                task_id=task.task_id,
                query=lead_query,
                evidence_ids=[item.evidence_id for item in added_evidence],
                average_quality=analysis.average_quality,
                decision=analysis.decision,
                details=analysis.reason,
            )
        )

        task.notes = analysis.reason
        if analysis.decision == "complete_task":
            task.status = "completed"
        elif analysis.decision == "refine_task":
            if task.attempts >= runtime_config.max_queries_per_task:
                task.status = "failed"
                memory.add_warning(f"Tarea '{task.title}' marcada como fallida por limite de intentos.")
            else:
                task.status = "pending"
        else:
            task.status = "pending"

        if memory.all_tasks_completed():
            break

        if memory.has_stagnated(runtime_config.stagnation_limit):
            _maybe_refine_plan(llm=llm, memory=memory, runtime_config=runtime_config)

    fatal_error = ""
    if not memory.evidence:
        for warning in memory.warnings:
            normalized = (warning or "").strip()
            if not normalized:
                continue
            if normalized.lower().startswith("planner:"):
                continue
            if normalized.lower().startswith("query repetida descartada"):
                continue
            fatal_error = normalized
            break
        if not fatal_error:
            fatal_error = "No se encontraron fuentes relevantes en la investigacion profunda."

    report = ""
    if not fatal_error:
        report = generate_research_report(
            user_query=user_query,
            memory=memory,
            llm=llm,
            runtime_config=runtime_config,
        )

    return DeepResearchResult(
        report=report,
        sources=memory.top_sources(runtime_config.max_report_sources),
        raw_results=memory.raw_evidence_snapshot(),
        plan=memory.to_plan_snapshot(),
        iterations=memory.to_iteration_snapshot(),
        warnings=memory.warnings,
        error=fatal_error,
    )
