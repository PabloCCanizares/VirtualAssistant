from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TaskStatus = Literal["pending", "in_progress", "completed", "failed"]


@dataclass
class ResearchTask:
    task_id: str
    title: str
    objective: str
    priority: int = 50
    status: TaskStatus = "pending"
    attempts: int = 0
    notes: str = ""
    queries: list[str] = field(default_factory=list)


@dataclass
class ResearchEvidence:
    evidence_id: str
    task_id: str
    query: str
    title: str
    url: str
    snippet: str
    source_type: Literal["web", "internal"]
    provider: str
    score: float = 0.0
    quality: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchIteration:
    iteration: int
    task_id: str
    query: str
    evidence_ids: list[str]
    average_quality: float
    decision: str
    details: str = ""


@dataclass(frozen=True)
class DeepResearchRuntimeConfig:
    max_iterations: int = 6
    max_tasks: int = 5
    max_queries_per_task: int = 3
    quality_threshold: float = 0.62
    stagnation_limit: int = 2
    loop_repeat_limit: int = 2
    max_report_sources: int = 8
    internal_source_limit: int = 10
    parallel_queries: bool = True


@dataclass
class PlanningResult:
    tasks: list[ResearchTask]
    rationale: str


@dataclass
class AnalysisResult:
    average_quality: float
    evidence_count: int
    contradictions: list[str]
    decision: str
    reason: str


@dataclass
class DeepResearchResult:
    report: str
    sources: list[dict[str, Any]]
    raw_results: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    iterations: list[dict[str, Any]]
    warnings: list[str]
    error: str = ""
