import logging
import json

from langchain_core.messages import SystemMessage

from ai.prompts.writer_prompt import WRITER_PROMPT
from ai.services.llm_utils import LLMInvokeError, invoke_with_retry
from ai.state import AppState


logger = logging.getLogger(__name__)


def _normalize_sources(raw_sources):
    sources = []
    for item in raw_sources or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        title = (item.get("title") or "").strip() or url
        snippet = (item.get("snippet") or "").strip()
        sources.append({"title": title, "url": url, "snippet": snippet})
    return sources


def _build_sources_block(sources):
    if not sources:
        return ""
    lines = ["Fuentes:"]
    for idx, src in enumerate(sources, start=1):
        lines.append(f"- [{idx}] {src['title']} - {src['url']}")
    return "\n".join(lines)


def _append_missing_sources(draft, sources):
    text = (draft or "").strip()
    if not sources:
        return text

    missing = [src for src in sources if src["url"] not in text]
    if not missing:
        return text

    block = _build_sources_block(missing)
    if not text:
        return block
    return f"{text}\n\n{block}"


def writer_node(state: AppState, llm) -> AppState:
    notes = (
        state.get("deep_research_notes")
        or state.get("research_notes")
        or state.get("progress_analysis", "")
    )

    sources = _normalize_sources(state.get("deep_research_sources", []))
    messages = [
        SystemMessage(content=WRITER_PROMPT),
        SystemMessage(content=f"Notas de analisis:\n{notes}"),
    ]
    if sources:
        messages.append(
            SystemMessage(content=f"Fuentes disponibles (JSON): {json.dumps(sources, ensure_ascii=True)}")
        )
    messages.extend(state.get("messages", []))
    try:
        draft = invoke_with_retry(llm, messages, retries=1)
    except LLMInvokeError:
        logger.exception("writer_node: error invocando LLM")
        draft = "No pude generar una respuesta en este momento."

    draft = _append_missing_sources(draft, sources)
    return {"draft_response": draft}
