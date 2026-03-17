from __future__ import annotations

import json
from dataclasses import dataclass, field

from ai.deep_research.types import ResearchEvidence, ResearchIteration, ResearchTask


@dataclass
class DeepResearchMemory:
    user_query: str
    context_json: str = "{}"
    tasks: list[ResearchTask] = field(default_factory=list)
    evidence: list[ResearchEvidence] = field(default_factory=list)
    iterations: list[ResearchIteration] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    _seen_sources: set[str] = field(default_factory=set)
    _query_counts: dict[str, int] = field(default_factory=dict)
    _quality_history: list[float] = field(default_factory=list)

    def add_tasks(self, tasks: list[ResearchTask]) -> None:
        existing_ids = {task.task_id for task in self.tasks}
        for task in tasks:
            if task.task_id in existing_ids:
                continue
            self.tasks.append(task)

    def get_next_task(self) -> ResearchTask | None:
        pending = [t for t in self.tasks if t.status in {"pending", "in_progress"}]
        if not pending:
            return None
        pending.sort(key=lambda t: (t.status == "in_progress", t.priority, t.attempts))
        return pending[0]

    def register_query(self, task_id: str, query: str) -> int:
        key = f"{task_id}::{(query or '').strip().lower()}"
        count = self._query_counts.get(key, 0) + 1
        self._query_counts[key] = count
        return count

    def add_warning(self, warning: str) -> None:
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def add_evidence(self, evidence_batch: list[ResearchEvidence]) -> list[ResearchEvidence]:
        added = []
        for evidence in evidence_batch:
            fingerprint = (evidence.url or "").strip().lower() or (
                f"internal::{evidence.title.strip().lower()}::{evidence.snippet.strip().lower()}"
            )
            if not fingerprint or fingerprint in self._seen_sources:
                continue
            self._seen_sources.add(fingerprint)
            self.evidence.append(evidence)
            added.append(evidence)
        return added

    def add_iteration(self, iteration: ResearchIteration) -> None:
        self.iterations.append(iteration)
        self._quality_history.append(iteration.average_quality)

    def has_stagnated(self, limit: int) -> bool:
        if limit <= 0:
            return False
        if len(self._quality_history) < (limit + 1):
            return False
        window = self._quality_history[-(limit + 1) :]
        baseline = window[0]
        best_gain = max(window) - baseline
        return best_gain < 0.03

    def all_tasks_completed(self) -> bool:
        return bool(self.tasks) and all(task.status in {"completed", "failed"} for task in self.tasks)

    def task_completion_ratio(self) -> float:
        if not self.tasks:
            return 0.0
        completed = len([task for task in self.tasks if task.status == "completed"])
        return completed / len(self.tasks)

    def context_summary(self, max_chars: int = 1200) -> str:
        try:
            context = json.loads(self.context_json or "{}")
        except Exception:
            return ""
        compact = {
            "tasks": len(context.get("tasks", []) if isinstance(context, dict) else []),
            "goals": len(context.get("goals", []) if isinstance(context, dict) else []),
            "projects": len(context.get("projects", []) if isinstance(context, dict) else []),
            "events": len(context.get("events", []) if isinstance(context, dict) else []),
        }
        text = json.dumps(compact, ensure_ascii=True)
        return text[:max_chars]

    def planner_summary(self, max_sources: int = 4) -> str:
        top_sources = self.top_sources(max_sources)
        summary = {
            "query": self.user_query,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": task.status,
                    "attempts": task.attempts,
                    "notes": task.notes,
                }
                for task in self.tasks
            ],
            "iterations": [
                {
                    "iteration": it.iteration,
                    "task_id": it.task_id,
                    "decision": it.decision,
                    "avg_quality": round(it.average_quality, 3),
                }
                for it in self.iterations[-6:]
            ],
            "top_sources": top_sources,
            "warnings": self.warnings[-4:],
            "contradictions": self.contradictions[-4:],
        }
        return json.dumps(summary, ensure_ascii=True)

    def top_sources(self, limit: int) -> list[dict]:
        sorted_evidence = sorted(self.evidence, key=lambda item: item.quality, reverse=True)
        output = []
        for evidence in sorted_evidence[: max(0, limit)]:
            output.append(
                {
                    "title": evidence.title,
                    "url": evidence.url,
                    "snippet": evidence.snippet,
                    "provider": evidence.provider,
                    "source_type": evidence.source_type,
                    "score": round(evidence.score, 4),
                    "quality": round(evidence.quality, 4),
                }
            )
        return output

    def to_plan_snapshot(self) -> list[dict]:
        return [
            {
                "task_id": task.task_id,
                "title": task.title,
                "objective": task.objective,
                "priority": task.priority,
                "status": task.status,
                "attempts": task.attempts,
            }
            for task in self.tasks
        ]

    def to_iteration_snapshot(self) -> list[dict]:
        return [
            {
                "iteration": it.iteration,
                "task_id": it.task_id,
                "query": it.query,
                "decision": it.decision,
                "average_quality": round(it.average_quality, 4),
                "details": it.details,
            }
            for it in self.iterations
        ]

    def raw_evidence_snapshot(self) -> list[dict]:
        return [
            {
                "task_id": evidence.task_id,
                "query": evidence.query,
                "title": evidence.title,
                "url": evidence.url,
                "snippet": evidence.snippet,
                "provider": evidence.provider,
                "source_type": evidence.source_type,
                "score": evidence.score,
                "quality": evidence.quality,
                "raw": evidence.raw,
            }
            for evidence in self.evidence
        ]
