from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from langchain_core.messages import SystemMessage

from ai.config import DeepSearchConfig
from ai.deep_research.memory import DeepResearchMemory
from ai.deep_research.types import DeepResearchRuntimeConfig, ResearchEvidence, ResearchTask
from ai.services.deep_search_service import DeepSearchError
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry

logger = logging.getLogger(__name__)

WebSearchTool = Callable[[str], list[dict]] | Callable[..., list[dict]]

_STOP_WORDS = {
    "de",
    "la",
    "el",
    "y",
    "en",
    "un",
    "una",
    "que",
    "con",
    "para",
    "por",
    "del",
    "los",
    "las",
    "sobre",
    "como",
    "qué",
    "cual",
    "cuál",
}


def _extract_json_list(text: str) -> list[str]:
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("queries"), list):
            return [str(item).strip() for item in data.get("queries", []) if str(item).strip()]
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except Exception:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []

    try:
        data = json.loads(text[start : end + 1])
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except Exception:
        return []
    return []


def _tokenize(text: str) -> list[str]:
    terms = re.findall(r"[a-zA-Z0-9áéíóúüñ]{3,}", (text or "").lower())
    return [term for term in terms if term not in _STOP_WORDS]


def _query_overlap_score(query: str, text: str) -> float:
    query_terms = set(_tokenize(query))
    if not query_terms:
        return 0.0
    text_terms = set(_tokenize(text))
    if not text_terms:
        return 0.0
    overlap = len(query_terms.intersection(text_terms))
    return overlap / max(1, len(query_terms))


def _fallback_queries(task: ResearchTask, user_query: str, max_queries: int) -> list[str]:
    candidates = [
        task.objective,
        f"{task.objective} evidencia y fuentes fiables",
        f"{user_query} mejores practicas y evidencia",
    ]
    output = []
    for query in candidates:
        cleaned = re.sub(r"\s+", " ", (query or "").strip())
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= max_queries:
            break
    return output


def generate_task_queries(
    *,
    task: ResearchTask,
    memory: DeepResearchMemory,
    llm,
    runtime_config: DeepResearchRuntimeConfig,
) -> list[str]:
    max_queries = max(1, runtime_config.max_queries_per_task)
    prompt_messages = [
        SystemMessage(
            content=(
                "Eres un generador de queries de investigacion. Devuelve SOLO JSON valido con "
                "formato {\"queries\": [\"...\"]}. Propone consultas concretas, variadas y no redundantes."
            )
        ),
        SystemMessage(content=f"Consulta global: {memory.user_query}"),
        SystemMessage(content=f"Tarea actual: {task.title} | Objetivo: {task.objective}"),
        SystemMessage(content=f"Memoria resumida: {memory.planner_summary(max_sources=3)}"),
        SystemMessage(content=f"Numero maximo de queries: {max_queries}"),
    ]

    try:
        raw = invoke_with_retry(llm, prompt_messages, retries=1)
        generated = _extract_json_list(raw)
        queries = []
        for query in generated:
            cleaned = re.sub(r"\s+", " ", query).strip()
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
            if len(queries) >= max_queries:
                break
        if queries:
            return queries
    except LLMInvokeError:
        logger.exception("generate_task_queries: error invocando LLM")
    except Exception:
        logger.exception("generate_task_queries: fallo inesperado")

    return _fallback_queries(task, memory.user_query, max_queries=max_queries)


def _internal_documents(context_json: str) -> list[tuple[str, dict]]:
    try:
        parsed = json.loads(context_json or "{}")
    except Exception:
        return []
    if not isinstance(parsed, dict):
        return []

    docs = []
    for collection_name in ("projects", "goals", "tasks", "events"):
        items = parsed.get(collection_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                docs.append((collection_name, item))
    return docs


def search_internal_context(
    *,
    task_id: str,
    query: str,
    context_json: str,
    source_limit: int,
) -> list[ResearchEvidence]:
    docs = _internal_documents(context_json)
    if not docs:
        return []

    results: list[ResearchEvidence] = []
    for collection_name, item in docs:
        content = json.dumps(item, ensure_ascii=False)
        overlap = _query_overlap_score(query, content)
        if overlap < 0.18:
            continue

        item_id = str(item.get("_id") or item.get("id") or "unknown")
        title = str(item.get("nombre") or item.get("title") or item.get("name") or f"{collection_name}:{item_id}")
        snippet = re.sub(r"\s+", " ", content)[:280]
        results.append(
            ResearchEvidence(
                evidence_id=str(uuid.uuid4()),
                task_id=task_id,
                query=query,
                title=title,
                url=f"internal://{collection_name}/{item_id}",
                snippet=snippet,
                source_type="internal",
                provider="internal_context",
                score=overlap,
                raw={"collection": collection_name, "document": item},
            )
        )

    results.sort(key=lambda evidence: evidence.score, reverse=True)
    return results[: max(0, source_limit)]


def _web_search_single(
    query: str,
    *,
    search_config: DeepSearchConfig,
    web_search_tool: Callable[..., list[dict]],
) -> tuple[list[dict], str]:
    try:
        results = web_search_tool(query, config=search_config)
        return results, ""
    except DeepSearchError as exc:
        return [], str(exc)
    except Exception as exc:
        logger.exception("_web_search_single: fallo inesperado")
        return [], f"Error de busqueda: {exc}"


def run_research_step(
    *,
    task: ResearchTask,
    memory: DeepResearchMemory,
    llm,
    search_config: DeepSearchConfig,
    runtime_config: DeepResearchRuntimeConfig,
    web_search_tool: Callable[..., list[dict]],
) -> tuple[list[ResearchEvidence], list[str], list[str]]:
    queries = generate_task_queries(task=task, memory=memory, llm=llm, runtime_config=runtime_config)
    task.queries = queries

    warnings: list[str] = []
    accepted_queries: list[str] = []
    for query in queries:
        repeats = memory.register_query(task.task_id, query)
        if repeats > runtime_config.loop_repeat_limit:
            warnings.append(f"Query repetida descartada: '{query}'")
            continue
        accepted_queries.append(query)

    if not accepted_queries:
        return [], [], warnings

    web_results_by_query: dict[str, list[dict]] = {}
    if runtime_config.parallel_queries and len(accepted_queries) > 1:
        max_workers = min(3, len(accepted_queries))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                query: executor.submit(
                    _web_search_single,
                    query,
                    search_config=search_config,
                    web_search_tool=web_search_tool,
                )
                for query in accepted_queries
            }
            for query, future in futures.items():
                raw_results, error = future.result()
                web_results_by_query[query] = raw_results
                if error:
                    warnings.append(error)
    else:
        for query in accepted_queries:
            raw_results, error = _web_search_single(
                query,
                search_config=search_config,
                web_search_tool=web_search_tool,
            )
            web_results_by_query[query] = raw_results
            if error:
                warnings.append(error)

    evidence_batch: list[ResearchEvidence] = []
    for query in accepted_queries:
        for item in web_results_by_query.get(query, []):
            evidence_batch.append(
                ResearchEvidence(
                    evidence_id=str(uuid.uuid4()),
                    task_id=task.task_id,
                    query=query,
                    title=(item.get("title") or "").strip() or (item.get("url") or "Fuente"),
                    url=(item.get("url") or "").strip(),
                    snippet=(item.get("snippet") or "").strip(),
                    source_type="web",
                    provider=(item.get("provider") or search_config.provider),
                    score=float(item.get("score", 0.0) or 0.0),
                    raw=item,
                )
            )

        evidence_batch.extend(
            search_internal_context(
                task_id=task.task_id,
                query=query,
                context_json=memory.context_json,
                source_limit=runtime_config.internal_source_limit,
            )
        )

    return evidence_batch, accepted_queries, warnings
