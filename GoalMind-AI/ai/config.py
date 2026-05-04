import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env(env_dir: Optional[Path] = None) -> None:
    """Carga variables de entorno, priorizando el .env de la raíz del proyecto."""
    base_dir = env_dir or PROJECT_ROOT
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    openai_api_key: Optional[str]
    openai_model: str
    gemini_api_key: Optional[str]
    gemini_model: str
    groq_api_key: Optional[str]
    groq_model: str
    default_user_id: Optional[str]
    deep_search_enabled: bool
    deep_search_provider: str
    deep_search_api_key: Optional[str]
    deep_search_max_results: int
    deep_search_timeout_seconds: int
    deep_search_max_sources: int
    deep_search_mode_default: str
    deep_research_max_iterations: int
    deep_research_max_tasks: int
    deep_research_max_queries_per_task: int
    deep_research_quality_threshold: float
    deep_research_stagnation_limit: int
    deep_research_loop_repeat_limit: int
    deep_research_max_report_sources: int
    deep_research_internal_source_limit: int
    deep_research_parallel_queries: bool


@dataclass(frozen=True)
class DeepSearchConfig:
    enabled: bool
    provider: str
    api_key: Optional[str]
    max_results: int
    timeout_seconds: int
    max_sources: int
    mode_default: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except Exception:
            logger.warning("Valor inválido para %s=%r. Se usará default=%s", name, raw, default)
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_choice(name: str, allowed: set[str], default: str) -> str:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in allowed:
        return raw
    logger.warning(
        "Valor inválido para %s=%r. Permitidos: %s. Se usará default=%s",
        name,
        raw,
        sorted(allowed),
        default,
    )
    return default


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except Exception:
            logger.warning("Valor inválido para %s=%r. Se usará default=%s", name, raw, default)
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_settings() -> Settings:
    load_env()
    provider = _env_choice("LLM_PROVIDER", {"openai", "gemini", "groq"}, "openai")
    return Settings(
        llm_provider=provider,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        default_user_id=os.getenv("DEFAULT_USER_ID"),
        deep_search_enabled=_env_bool("DEEP_SEARCH_ENABLED", False),
        deep_search_provider=_env_choice(
            "DEEP_SEARCH_PROVIDER",
            {"tavily", "serper", "brave"},
            "tavily",
        ),
        deep_search_api_key=os.getenv("DEEP_SEARCH_API_KEY"),
        deep_search_max_results=_env_int("DEEP_SEARCH_MAX_RESULTS", 8, minimum=1, maximum=20),
        deep_search_timeout_seconds=_env_int(
            "DEEP_SEARCH_TIMEOUT_SECONDS",
            10,
            minimum=3,
            maximum=60,
        ),
        deep_search_max_sources=_env_int("DEEP_SEARCH_MAX_SOURCES", 5, minimum=1, maximum=12),
        deep_search_mode_default=_env_choice(
            "DEEP_SEARCH_MODE_DEFAULT",
            {"auto", "on", "off"},
            "auto",
        ),
        deep_research_max_iterations=_env_int("DEEP_RESEARCH_MAX_ITERATIONS", 6, minimum=1, maximum=15),
        deep_research_max_tasks=_env_int("DEEP_RESEARCH_MAX_TASKS", 5, minimum=1, maximum=12),
        deep_research_max_queries_per_task=_env_int(
            "DEEP_RESEARCH_MAX_QUERIES_PER_TASK",
            3,
            minimum=1,
            maximum=8,
        ),
        deep_research_quality_threshold=_env_float(
            "DEEP_RESEARCH_QUALITY_THRESHOLD",
            0.62,
            minimum=0.0,
            maximum=1.0,
        ),
        deep_research_stagnation_limit=_env_int(
            "DEEP_RESEARCH_STAGNATION_LIMIT",
            2,
            minimum=1,
            maximum=8,
        ),
        deep_research_loop_repeat_limit=_env_int(
            "DEEP_RESEARCH_LOOP_REPEAT_LIMIT",
            2,
            minimum=1,
            maximum=6,
        ),
        deep_research_max_report_sources=_env_int(
            "DEEP_RESEARCH_MAX_REPORT_SOURCES",
            8,
            minimum=1,
            maximum=20,
        ),
        deep_research_internal_source_limit=_env_int(
            "DEEP_RESEARCH_INTERNAL_SOURCE_LIMIT",
            10,
            minimum=0,
            maximum=30,
        ),
        deep_research_parallel_queries=_env_bool("DEEP_RESEARCH_PARALLEL_QUERIES", True),
    )


def get_deep_search_config(settings: Settings | None = None) -> DeepSearchConfig:
    current = settings or get_settings()
    return DeepSearchConfig(
        enabled=current.deep_search_enabled,
        provider=current.deep_search_provider,
        api_key=current.deep_search_api_key,
        max_results=current.deep_search_max_results,
        timeout_seconds=current.deep_search_timeout_seconds,
        max_sources=current.deep_search_max_sources,
        mode_default=current.deep_search_mode_default,
    )


def get_deep_research_runtime_config(settings: Settings | None = None):
    from ai.deep_research.types import DeepResearchRuntimeConfig

    current = settings or get_settings()
    return DeepResearchRuntimeConfig(
        max_iterations=current.deep_research_max_iterations,
        max_tasks=current.deep_research_max_tasks,
        max_queries_per_task=current.deep_research_max_queries_per_task,
        quality_threshold=current.deep_research_quality_threshold,
        stagnation_limit=current.deep_research_stagnation_limit,
        loop_repeat_limit=current.deep_research_loop_repeat_limit,
        max_report_sources=current.deep_research_max_report_sources,
        internal_source_limit=current.deep_research_internal_source_limit,
        parallel_queries=current.deep_research_parallel_queries,
    )


def build_llm(model: str | None = None):
    """Factory: devuelve el LLM correcto segun LLM_PROVIDER del .env."""
    settings = get_settings()
    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model or settings.gemini_model)
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model or settings.groq_model)
    else:
        from langchain_openai import ChatOpenAI
        # gpt-5-nano solo acepta temperature por defecto (=1) en chat completions.
        return ChatOpenAI(model=model or settings.openai_model, temperature=1)
