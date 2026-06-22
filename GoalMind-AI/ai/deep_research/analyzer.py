from __future__ import annotations

import re
from urllib.parse import urlparse

from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.types import (
    AnalysisResult,
    DeepResearchRuntimeConfig,
    ResearchEvidence,
    ResearchTask,
)

_CREDIBLE_TLDS = {".gov", ".edu", ".org"}
_AFFIRM_TERMS = {"eficaz", "recomendado", "beneficioso", "mejora", "aumenta", "sirve"}
_NEGATE_TERMS = {"ineficaz", "no", "nunca", "mito", "falso", "reduce"}


def _safe_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _domain_bonus(url: str) -> float:
    domain = _safe_domain(url)
    if not domain:
        return 0.0
    if any(domain.endswith(tld) for tld in _CREDIBLE_TLDS):
        return 0.2
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.count(".") >= 2:
        return 0.08
    return 0.04


def _normalize_source_score(evidence: ResearchEvidence) -> float:
    value = float(evidence.score or 0.0)
    if evidence.provider == "serper" and value > 0:
        # Serper expone "position" donde 1 es mejor. Lo invertimos suavemente.
        return max(0.0, min(1.0, 1.0 / value))
    if value <= 1.0:
        return max(0.0, value)
    return max(0.0, min(1.0, value / 10.0))


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9áéíóúüñ]{3,}", (text or "").lower()))


def _relevance_score(query: str, evidence: ResearchEvidence) -> float:
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0
    text_terms = _tokenize(f"{evidence.title} {evidence.snippet}")
    overlap = len(query_terms.intersection(text_terms))
    return max(0.0, min(1.0, overlap / len(query_terms)))


def score_evidence_quality(query: str, evidence: ResearchEvidence) -> float:
    source_score = _normalize_source_score(evidence)
    relevance = _relevance_score(query, evidence)
    snippet_size = min(1.0, len((evidence.snippet or "").strip()) / 260)
    domain_bonus = _domain_bonus(evidence.url)
    internal_bonus = 0.1 if evidence.source_type == "internal" else 0.0

    quality = (0.4 * source_score) + (0.3 * relevance) + (0.2 * snippet_size) + domain_bonus + internal_bonus
    return max(0.0, min(1.0, quality))


def _detect_contradictions(evidence_batch: list[ResearchEvidence]) -> list[str]:
    contradictions: list[str] = []
    for idx, left in enumerate(evidence_batch):
        left_terms = _tokenize(left.snippet)
        if not left_terms:
            continue
        left_affirm = bool(_AFFIRM_TERMS.intersection(left_terms))
        left_negate = bool(_NEGATE_TERMS.intersection(left_terms))

        for right in evidence_batch[idx + 1 :]:
            right_terms = _tokenize(right.snippet)
            if not right_terms:
                continue

            shared = left_terms.intersection(right_terms)
            if len(shared) < 3:
                continue

            right_affirm = bool(_AFFIRM_TERMS.intersection(right_terms))
            right_negate = bool(_NEGATE_TERMS.intersection(right_terms))
            if (left_affirm and right_negate) or (left_negate and right_affirm):
                contradictions.append(
                    (
                        "Posible contradiccion entre fuentes: "
                        f"'{left.title}' vs '{right.title}'"
                    )
                )
                if len(contradictions) >= 3:
                    return contradictions
    return contradictions


def evaluate_research_step(
    *,
    task: ResearchTask,
    evidence_batch: list[ResearchEvidence],
    accepted_queries: list[str],
    memory: DeepResearchMemory,
    runtime_config: DeepResearchRuntimeConfig,
) -> AnalysisResult:
    if not accepted_queries:
        return AnalysisResult(
            average_quality=0.0,
            evidence_count=0,
            contradictions=[],
            decision="refine_task",
            reason="No se pudieron generar queries validas para esta tarea.",
        )

    if not evidence_batch:
        return AnalysisResult(
            average_quality=0.0,
            evidence_count=0,
            contradictions=[],
            decision="refine_task",
            reason="No se recupero evidencia util en esta iteracion.",
        )

    query_for_scoring = accepted_queries[0]
    for evidence in evidence_batch:
        evidence.quality = score_evidence_quality(query_for_scoring, evidence)

    average_quality = sum(item.quality for item in evidence_batch) / max(1, len(evidence_batch))
    contradictions = _detect_contradictions(evidence_batch)
    if contradictions:
        for contradiction in contradictions:
            if contradiction not in memory.contradictions:
                memory.contradictions.append(contradiction)

    if average_quality >= runtime_config.quality_threshold and len(evidence_batch) >= 2:
        return AnalysisResult(
            average_quality=average_quality,
            evidence_count=len(evidence_batch),
            contradictions=contradictions,
            decision="complete_task",
            reason="Calidad y cobertura suficientes para dar la tarea por completada.",
        )

    if task.attempts >= runtime_config.max_queries_per_task:
        return AnalysisResult(
            average_quality=average_quality,
            evidence_count=len(evidence_batch),
            contradictions=contradictions,
            decision="complete_task",
            reason="Se alcanzo el maximo de intentos por tarea.",
        )

    if memory.has_stagnated(runtime_config.stagnation_limit):
        return AnalysisResult(
            average_quality=average_quality,
            evidence_count=len(evidence_batch),
            contradictions=contradictions,
            decision="complete_task",
            reason="Se detecto estancamiento de calidad en iteraciones recientes.",
        )

    return AnalysisResult(
        average_quality=average_quality,
        evidence_count=len(evidence_batch),
        contradictions=contradictions,
        decision="continue",
        reason="Calidad parcial: se recomienda iterar con nuevas queries.",
    )
