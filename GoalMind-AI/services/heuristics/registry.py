"""Registry and execution helpers for deterministic heuristics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.heuristics.atomic import HEURISTICS, build_indexes
from services.heuristics.types import (
    HeuristicContext,
    bounded_limit,
    normalize_categories,
    normalize_parameters,
    sort_findings,
)
from services.user_context_service import get_user_dataset, serialize_value


def list_heuristics(categories: list[str] | tuple[str, ...] | str | None = None) -> list[dict]:
    selected_categories = normalize_categories(categories)
    rows = []
    for heuristic in HEURISTICS:
        if selected_categories and heuristic.category not in selected_categories:
            continue
        rows.append(
            {
                "name": heuristic.name,
                "description": heuristic.description,
                "category": heuristic.category,
                "base_severity": heuristic.severity,
            }
        )
    return rows


def explain_heuristic(name: str) -> dict | None:
    for heuristic in HEURISTICS:
        if heuristic.name == name:
            return {
                "name": heuristic.name,
                "description": heuristic.description,
                "category": heuristic.category,
                "base_severity": heuristic.severity,
            }
    return None


def run_atomic_findings(
    usuario_id: str | None = None,
    *,
    categories: list[str] | tuple[str, ...] | str | None = None,
    limit: int | str | None = 100,
    now: datetime | None = None,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    parameters = normalize_parameters(
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    selected_categories = normalize_categories(categories)
    dataset = get_user_dataset(usuario_id=usuario_id)
    ctx = HeuristicContext(
        dataset=dataset,
        indexes=build_indexes(dataset),
        now=current,
        parameters=parameters,
    )

    findings = []
    executed = []
    for heuristic in HEURISTICS:
        if selected_categories and heuristic.category not in selected_categories:
            continue
        executed.append(heuristic.name)
        findings.extend(heuristic.evaluator(ctx))

    findings = sort_findings(findings)
    bounded = bounded_limit(limit, default=100, maximum=500)
    returned = findings[:bounded]

    counts_by_type: dict[str, int] = {}
    counts_by_category: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("type"))
        category = str(finding.get("category"))
        counts_by_type[kind] = counts_by_type.get(kind, 0) + 1
        counts_by_category[category] = counts_by_category.get(category, 0) + 1

    return {
        "user_id": dataset["user_id"],
        "generated_at": serialize_value(current),
        "parameters": parameters,
        "categories": sorted(selected_categories) if selected_categories else None,
        "heuristics": executed,
        "counts_by_type": counts_by_type,
        "counts_by_category": counts_by_category,
        "total": len(findings),
        "returned": len(returned),
        "findings": returned,
    }
