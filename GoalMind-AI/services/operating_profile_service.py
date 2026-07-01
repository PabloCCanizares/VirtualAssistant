"""Deterministic operating profile for GoalMind AI agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.emergent_insight_service import analyze_operating_system
from services.heuristics.types import bounded_limit
from services.user_context_service import serialize_value

SEVERITY_PENALTY = {"high": 14, "medium": 8, "low": 3, "info": 1}
IMPACT_PENALTY = {"high": 12, "medium": 7, "low": 3}

DIMENSIONS = {
    "structure": {
        "title": "Estructura",
        "categories": {"structure"},
        "description": "Claridad entre proyectos, objetivos y tareas.",
    },
    "time": {
        "title": "Tiempo",
        "categories": {"time"},
        "description": "Fechas, vencimientos y calendario operativo.",
    },
    "load": {
        "title": "Carga",
        "categories": {"load"},
        "description": "Volumen activo de proyectos, objetivos y tareas.",
    },
    "data_quality": {
        "title": "Calidad de datos",
        "categories": {"data_quality"},
        "description": "Información mínima para razonar bien.",
    },
    "progress": {
        "title": "Progreso",
        "categories": {"progress"},
        "description": "Coherencia entre avance declarado y ejecución real.",
    },
}


def _status_for_score(score: int) -> str:
    if score >= 85:
        return "healthy"
    if score >= 70:
        return "watch"
    if score >= 50:
        return "attention"
    return "critical"


def _penalty_for_finding(finding: dict[str, Any]) -> int:
    return SEVERITY_PENALTY.get(str(finding.get("severity") or ""), 2)


def _penalty_for_insight(insight: dict[str, Any]) -> int:
    penalty = IMPACT_PENALTY.get(str(insight.get("impact") or ""), 2)
    confidence = insight.get("confidence")
    try:
        confidence_factor = float(confidence)
    except (TypeError, ValueError):
        confidence_factor = 1.0
    return max(1, round(penalty * min(max(confidence_factor, 0.2), 1.0)))


def _compact_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": finding.get("type"),
        "category": finding.get("category"),
        "severity": finding.get("severity"),
        "entity": finding.get("entity"),
        "explanation": finding.get("explanation"),
        "recommendation": finding.get("recommendation"),
    }


def _compact_insight(insight: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": insight.get("type"),
        "category": insight.get("category"),
        "title": insight.get("title"),
        "summary": insight.get("summary"),
        "confidence": insight.get("confidence"),
        "impact": insight.get("impact"),
        "recommendation": insight.get("recommendation"),
        "related_entities": insight.get("related_entities") or [],
    }


def _build_dimensions(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    dimensions = {}
    for name, config in DIMENSIONS.items():
        related = [
            finding
            for finding in findings
            if str(finding.get("category") or "") in config["categories"]
        ]
        penalty = min(sum(_penalty_for_finding(finding) for finding in related), 100)
        score = max(0, 100 - penalty)
        dimensions[name] = {
            "title": config["title"],
            "description": config["description"],
            "score": score,
            "status": _status_for_score(score),
            "finding_count": len(related),
            "top_findings": [_compact_finding(finding) for finding in related[:5]],
        }
    return dimensions


def _build_explanation(
    score: int,
    findings: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    dimensions: dict[str, dict[str, Any]],
) -> list[str]:
    if not findings and not insights:
        return [
            "No hay señales relevantes en las heurísticas actuales.",
            "El perfil queda alto porque no se detectan bloqueos, deuda temporal ni incoherencias de progreso.",
        ]

    weakest_dimensions = sorted(dimensions.values(), key=lambda item: item["score"])[:2]
    lines = [
        f"El score operativo es {score}/100 por la combinación de {len(findings)} hallazgos atómicos y {len(insights)} patrones emergentes.",
    ]
    if weakest_dimensions:
        labels = ", ".join(
            f"{dimension['title']} ({dimension['score']})" for dimension in weakest_dimensions
        )
        lines.append(f"Las dimensiones que más tiran hacia abajo son: {labels}.")
    if insights:
        top = insights[0]
        lines.append(
            f"El patrón dominante es '{top.get('title')}' con impacto {top.get('impact')} y confianza {top.get('confidence')}."
        )
    return lines


def _score(findings: list[dict[str, Any]], insights: list[dict[str, Any]]) -> int:
    atomic_penalty = sum(_penalty_for_finding(finding) for finding in findings)
    insight_penalty = sum(_penalty_for_insight(insight) for insight in insights)
    return max(0, min(100, 100 - min(95, atomic_penalty + insight_penalty)))


def build_operating_profile(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
    limit: int | str | None = 10,
    **parameters,
) -> dict[str, Any]:
    """Return a compact deterministic profile for agent decision making."""
    bounded = bounded_limit(limit, default=10, maximum=50)
    analysis = analyze_operating_system(
        usuario_id=usuario_id,
        now=now,
        limit=max(bounded, 20),
        **parameters,
    )
    findings = analysis["atomic_findings"]["findings"]
    insights = analysis["emergent_insights"]["insights"]
    dimensions = _build_dimensions(findings)
    overall_score = _score(findings, insights)
    high_findings = [
        _compact_finding(finding) for finding in findings if finding.get("severity") == "high"
    ]
    high_insights = [
        _compact_insight(insight) for insight in insights if insight.get("impact") == "high"
    ]

    actions = []
    seen = set()
    for action in analysis["suggested_actions"]:
        key = (action.get("tool"), str(sorted((action.get("payload") or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        actions.append(action)

    profile = {
        "user_id": analysis["user_id"],
        "generated_at": analysis["generated_at"],
        "score": {
            "overall": overall_score,
            "status": _status_for_score(overall_score),
        },
        "dimensions": dimensions,
        "dominant_patterns": [_compact_insight(insight) for insight in insights[:bounded]],
        "top_risks": (high_insights + high_findings)[:bounded],
        "top_opportunities": analysis["opportunities"][:bounded],
        "next_best_moves": serialize_value(actions[:bounded]),
        "explanation": _build_explanation(overall_score, findings, insights, dimensions),
        "source": {
            "atomic_finding_count": analysis["atomic_findings"]["total"],
            "emergent_insight_count": analysis["emergent_insights"]["total"],
            "snapshot_counts": analysis["snapshot"]["counts"],
        },
    }
    return serialize_value(profile)
