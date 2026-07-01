"""Common contracts for deterministic GoalMind AI heuristics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from services.user_context_service import serialize_value

DEFAULT_HEURISTIC_PARAMETERS = {
    "stale_days": 30,
    "due_soon_days": 7,
    "overloaded_task_threshold": 8,
    "max_active_projects": 6,
    "max_pending_tasks": 30,
    "low_progress_threshold": 25,
}

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class HeuristicContext:
    dataset: dict[str, Any]
    indexes: dict[str, Any]
    now: datetime
    parameters: dict[str, int]


@dataclass(frozen=True)
class HeuristicDefinition:
    name: str
    description: str
    category: str
    severity: str
    evaluator: Callable[[HeuristicContext], list[dict[str, Any]]]


def normalize_parameters(**overrides: Any) -> dict[str, int]:
    params = dict(DEFAULT_HEURISTIC_PARAMETERS)
    for key, default in DEFAULT_HEURISTIC_PARAMETERS.items():
        value = overrides.get(key, default)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        params[key] = max(1, parsed)
    return params


def normalize_categories(categories: list[str] | tuple[str, ...] | str | None) -> set[str] | None:
    if categories is None:
        return None
    if isinstance(categories, str):
        raw = [part.strip() for part in categories.split(",")]
    else:
        raw = [str(part).strip() for part in categories]
    selected = {part for part in raw if part}
    return selected or None


def bounded_limit(limit: int | str | None, *, default: int = 100, maximum: int = 500) -> int:
    try:
        parsed = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def make_finding(
    *,
    kind: str,
    category: str,
    severity: str,
    entity: dict[str, Any],
    evidence: dict[str, Any],
    explanation: str,
    recommendation: str,
    suggested_tool: str | None = None,
    suggested_payload: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "type": kind,
        "category": category,
        "severity": severity,
        "entity": serialize_value(entity),
        "evidence": serialize_value(evidence),
        "confidence": round(float(confidence), 2),
        "explanation": explanation,
        "recommendation": recommendation,
        "suggested_tool": suggested_tool,
        "suggested_payload": serialize_value(suggested_payload or {}),
        "requires_confirmation": bool(requires_confirmation),
    }


def finding_sort_key(finding: dict[str, Any]) -> tuple[int, str, str]:
    return (
        SEVERITY_RANK.get(str(finding.get("severity")), 9),
        str(finding.get("category") or ""),
        str(finding.get("type") or ""),
    )


def sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(findings, key=finding_sort_key)
