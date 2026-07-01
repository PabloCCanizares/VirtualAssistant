"""Portfolio-level analysis and action suggestions for GoalMind AI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.emergent_insight_service import find_emergent_insights
from services.heuristics.registry import run_atomic_findings


def _priority_for(item: dict) -> str:
    severity_or_impact = item.get("severity") or item.get("impact")
    if severity_or_impact == "high":
        return "alta"
    if severity_or_impact == "medium":
        return "media"
    return "baja"


def _action_key(action: dict) -> tuple[str, str]:
    payload = action.get("suggested_payload") or action.get("payload") or {}
    return (
        str(action.get("suggested_tool") or action.get("tool") or ""),
        str(sorted(payload.items())),
    )


def _suggestion_from_finding(finding: dict) -> dict[str, Any] | None:
    tool = finding.get("suggested_tool")
    if not tool:
        return None
    return {
        "type": f"resolve_{finding.get('type')}",
        "reason": finding.get("recommendation"),
        "related_entity": finding.get("entity"),
        "priority": _priority_for(finding),
        "suggested_tool": tool,
        "suggested_payload": finding.get("suggested_payload") or {},
        "requires_confirmation": bool(finding.get("requires_confirmation")),
        "confidence": finding.get("confidence"),
    }


def _suggestion_from_insight_action(insight: dict, action: dict) -> dict[str, Any]:
    return {
        "type": f"act_on_{insight.get('type')}",
        "reason": insight.get("recommendation"),
        "related_entity": (insight.get("related_entities") or [{}])[0],
        "priority": _priority_for(insight),
        "suggested_tool": action.get("tool"),
        "suggested_payload": action.get("payload") or {},
        "requires_confirmation": bool(action.get("requires_confirmation")),
        "confidence": insight.get("confidence"),
    }


def suggest_next_actions(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int = 10,
    categories: list[str] | tuple[str, ...] | str | None = None,
    stale_days: int = 30,
    due_soon_days: int = 7,
    overloaded_task_threshold: int = 8,
    max_active_projects: int = 6,
    max_pending_tasks: int = 30,
    low_progress_threshold: int = 25,
) -> dict:
    current = now or datetime.utcnow()
    atomic = run_atomic_findings(
        usuario_id=usuario_id,
        categories=categories,
        limit=500,
        now=current,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )
    emergent = find_emergent_insights(
        usuario_id=atomic["user_id"],
        atomic_findings=atomic,
        now=current,
        limit=50,
        stale_days=stale_days,
        due_soon_days=due_soon_days,
        overloaded_task_threshold=overloaded_task_threshold,
        max_active_projects=max_active_projects,
        max_pending_tasks=max_pending_tasks,
        low_progress_threshold=low_progress_threshold,
    )

    suggestions = []
    seen = set()
    for insight in emergent["insights"]:
        for action in insight.get("suggested_actions") or []:
            suggestion = _suggestion_from_insight_action(insight, action)
            key = _action_key(suggestion)
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(suggestion)

    for finding in atomic["findings"]:
        suggestion = _suggestion_from_finding(finding)
        if suggestion is None:
            continue
        key = _action_key(suggestion)
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(suggestion)

    priority_rank = {"alta": 0, "media": 1, "baja": 2}
    suggestions.sort(key=lambda item: priority_rank.get(item.get("priority"), 9))
    bounded_limit = max(1, min(int(limit or 10), 50))

    return {
        "user_id": atomic["user_id"],
        "generated_at": atomic["generated_at"],
        "source": {
            "atomic_counts_by_type": atomic["counts_by_type"],
            "emergent_insight_count": emergent["total"],
        },
        "actions": suggestions[:bounded_limit],
    }
