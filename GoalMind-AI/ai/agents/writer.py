import logging
from typing import Any

from langchain_core.messages import SystemMessage

from ai.prompts.writer_prompt import WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def _normalize_sources(sources: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "url": url,
                "title": str(source.get("title") or url).strip(),
                "snippet": str(source.get("snippet") or "").strip(),
            }
        )
    return normalized


def _build_sources_block(sources: list[dict[str, Any]] | None) -> str:
    normalized = _normalize_sources(sources)
    if not normalized:
        return ""
    lines = ["Fuentes:"]
    for idx, source in enumerate(normalized, 1):
        title = source["title"] or source["url"]
        snippet = source["snippet"]
        line = f"{idx}. {title} - {source['url']}"
        if snippet:
            line = f"{line} ({snippet})"
        lines.append(line)
    return "\n".join(lines)


def _append_missing_sources(text: str, sources: list[dict[str, Any]] | None) -> str:
    current = (text or "").strip()
    missing = [source for source in _normalize_sources(sources) if source["url"] not in current]
    block = _build_sources_block(missing)
    if not block:
        return current
    return f"{current}\n\n{block}" if current else block


def writer_node(state: AppState, llm) -> AppState:
    # Usa research_notes o progress_analysis, sin context_json crudo
    notes = state.get("research_notes") or state.get("progress_analysis", "")
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Notas de analisis:\n{notes}"),
    ]
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages)
    except LLMInvokeError:
        logger.exception("writer_node: error invocando LLM")
        draft = "No pude generar una respuesta en este momento."
    draft = _append_missing_sources(draft, state.get("deep_research_sources"))
    return {"draft_response": draft}

