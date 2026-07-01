"""Pattern and bottleneck detection for GoalMind AI."""

from __future__ import annotations

from datetime import datetime

from services.heuristics.registry import run_atomic_findings


def find_atomic_findings(
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
) -> dict:
    return run_atomic_findings(
        usuario_id=usuario_id,
        categories=categories,
        limit=limit,
        now=now,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )


def find_bottlenecks(
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
) -> dict:
    """Backward-compatible wrapper around atomic findings."""
    analysis = find_atomic_findings(
        usuario_id=usuario_id,
        categories=categories,
        limit=limit,
        now=now,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    return {
        **analysis,
        "bottlenecks": analysis["findings"],
    }
