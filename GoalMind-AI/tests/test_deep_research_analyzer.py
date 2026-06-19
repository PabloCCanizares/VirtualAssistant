"""Tests para deep_research/analyzer: scoring, dominios y deteccion de contradicciones."""

from __future__ import annotations

import pytest

from ai.deep_research import analyzer
from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.types import DeepResearchRuntimeConfig, ResearchEvidence, ResearchTask


def _evidence(**overrides):
    base = dict(
        evidence_id="e1",
        task_id="t1",
        query="q",
        title="t",
        url="https://example.com",
        snippet="snippet",
        source_type="web",
        provider="tavily",
        score=0.5,
        quality=0.0,
    )
    base.update(overrides)
    return ResearchEvidence(**base)


class TestSafeDomain:
    def test_extracts_netloc(self):
        assert analyzer._safe_domain("https://www.example.com/path") == "www.example.com"

    def test_handles_empty_input(self):
        assert analyzer._safe_domain("") == ""
        assert analyzer._safe_domain(None) == ""  # type: ignore[arg-type]

    def test_lowercases_result(self):
        assert analyzer._safe_domain("https://EXAMPLE.com") == "example.com"


class TestDomainBonus:
    def test_credible_tld_gov(self):
        assert analyzer._domain_bonus("https://nih.gov") == 0.2

    def test_credible_tld_edu(self):
        assert analyzer._domain_bonus("https://mit.edu") == 0.2

    def test_credible_tld_org(self):
        assert analyzer._domain_bonus("https://wikipedia.org") == 0.2

    def test_subdomain_bonus(self):
        # 'www.example.com' -> tras stripping www. son 2 puntos en 'example.com' (1 punto), no califica
        # 'foo.example.com' -> 2 puntos
        assert analyzer._domain_bonus("https://blog.example.com") == 0.08

    def test_default_for_simple_domain(self):
        assert analyzer._domain_bonus("https://example.com") == 0.04

    def test_strips_www_before_count(self):
        # www.example.com -> example.com (1 punto) -> 0.04
        assert analyzer._domain_bonus("https://www.example.com") == 0.04

    def test_zero_for_empty_url(self):
        assert analyzer._domain_bonus("") == 0.0


class TestNormalizeSourceScore:
    def test_serper_position_one_inverted_to_one(self):
        ev = _evidence(provider="serper", score=1)
        assert analyzer._normalize_source_score(ev) == pytest.approx(1.0)

    def test_serper_position_two_inverted_to_half(self):
        ev = _evidence(provider="serper", score=2)
        assert analyzer._normalize_source_score(ev) == pytest.approx(0.5)

    def test_score_in_unit_range_passthrough(self):
        ev = _evidence(provider="tavily", score=0.7)
        assert analyzer._normalize_source_score(ev) == pytest.approx(0.7)

    def test_score_above_one_normalized(self):
        ev = _evidence(provider="tavily", score=5.0)
        assert analyzer._normalize_source_score(ev) == pytest.approx(0.5)

    def test_score_above_ten_clamped_to_one(self):
        ev = _evidence(provider="tavily", score=99)
        assert analyzer._normalize_source_score(ev) == pytest.approx(1.0)

    def test_zero_score(self):
        ev = _evidence(provider="serper", score=0)
        assert analyzer._normalize_source_score(ev) == 0.0


class TestTokenize:
    def test_lowercases_and_filters_short_words(self):
        assert analyzer._tokenize("La casa es Bonita") == {"casa", "bonita"}

    def test_supports_spanish_accents(self):
        assert "investigación" in analyzer._tokenize("Investigación científica")

    def test_empty_returns_empty_set(self):
        assert analyzer._tokenize("") == set()
        assert analyzer._tokenize(None) == set()  # type: ignore[arg-type]

    def test_strips_punctuation(self):
        toks = analyzer._tokenize("Hola, mundo! Esto es Python.")
        assert "hola" in toks
        assert "mundo" in toks
        assert "python" in toks


class TestRelevanceScore:
    def test_zero_when_query_empty(self):
        ev = _evidence(title="cualquier", snippet="cosa")
        assert analyzer._relevance_score("", ev) == 0.0

    def test_zero_when_no_overlap(self):
        ev = _evidence(title="banana", snippet="manzana")
        assert analyzer._relevance_score("python flask", ev) == 0.0

    def test_full_overlap_score_one(self):
        ev = _evidence(title="python flask", snippet="")
        assert analyzer._relevance_score("python flask", ev) == 1.0

    def test_partial_overlap_proportional(self):
        ev = _evidence(title="python tutorial", snippet="basics")
        assert analyzer._relevance_score("python flask", ev) == pytest.approx(0.5)


class TestScoreEvidenceQuality:
    def test_quality_stays_in_unit_interval(self):
        ev = _evidence(provider="tavily", score=1.0, snippet="s" * 500, url="https://nih.gov")
        q = analyzer.score_evidence_quality("query", ev)
        assert 0.0 <= q <= 1.0

    def test_internal_source_gets_bonus(self):
        ev_int = _evidence(source_type="internal", score=0.5, url="")
        ev_web = _evidence(source_type="web", score=0.5, url="")
        # Mismo score base; solo difiere en internal_bonus (+0.1)
        q_int = analyzer.score_evidence_quality("query irrelevante", ev_int)
        q_web = analyzer.score_evidence_quality("query irrelevante", ev_web)
        assert q_int >= q_web


class TestEvaluateResearchStep:
    def test_no_queries_marks_refine_task(self):
        result = analyzer.evaluate_research_step(
            task=ResearchTask(task_id="t", title="x", objective="y"),
            evidence_batch=[_evidence()],
            accepted_queries=[],
            memory=DeepResearchMemory(user_query="q"),
            runtime_config=DeepResearchRuntimeConfig(),
        )
        assert result.decision == "refine_task"
        assert result.evidence_count == 0

    def test_no_evidence_marks_refine_task(self):
        result = analyzer.evaluate_research_step(
            task=ResearchTask(task_id="t", title="x", objective="y"),
            evidence_batch=[],
            accepted_queries=["q"],
            memory=DeepResearchMemory(user_query="q"),
            runtime_config=DeepResearchRuntimeConfig(),
        )
        assert result.decision == "refine_task"

    def test_max_attempts_force_complete(self):
        cfg = DeepResearchRuntimeConfig(max_queries_per_task=1, quality_threshold=0.99)
        task = ResearchTask(task_id="t", title="x", objective="y", attempts=2)
        result = analyzer.evaluate_research_step(
            task=task,
            evidence_batch=[_evidence(score=0.1)],
            accepted_queries=["q"],
            memory=DeepResearchMemory(user_query="q"),
            runtime_config=cfg,
        )
        assert result.decision == "complete_task"
        assert "maximo de intentos" in result.reason.lower()
