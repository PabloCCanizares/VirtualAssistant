import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


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
    openai_timeout_seconds: int
    ai_llm_retries: int
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


@dataclass(frozen=True)
class DeepSearchRuntimeConfig:
    max_iterations: int
    max_tasks: int
    max_queries_per_task: int
    quality_threshold: float
    stagnation_limit: int
    loop_repeat_limit: int
    max_report_sources: int
    internal_source_limit: int
    parallel_queries: bool


@dataclass(frozen=True)
class ChatModelOption:
    id: str
    provider: str
    model: str
    api_key: Optional[str]
    label: str

    @property
    def available(self) -> bool:
        return bool((self.api_key or "").strip())


def _build_model_options(settings: Settings) -> list[ChatModelOption]:
    return [
        ChatModelOption(
            id="openai",
            provider="openai",
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            label=f"OpenAI · {settings.openai_model}",
        ),
        ChatModelOption(
            id="gemini",
            provider="gemini",
            model=settings.gemini_model,
            api_key=settings.gemini_api_key,
            label=f"Gemini · {settings.gemini_model}",
        ),
        ChatModelOption(
            id="groq",
            provider="groq",
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            label=f"Groq · {settings.groq_model}",
        ),
    ]


def get_chat_model_catalog(settings: Optional[Settings] = None) -> dict:
    current = settings or get_settings()
    options = _build_model_options(current)

    default = next((option for option in options if option.available), options[0] if options else None)
    return {
        "default_model_id": default.id if default else None,
        "models": [
            {
                "id": option.id,
                "provider": option.provider,
                "model": option.model,
                "label": option.label,
                "available": option.available,
            }
            for option in options
        ],
    }


def resolve_chat_model(settings: Settings, model_id: Optional[str]) -> ChatModelOption:
    options = _build_model_options(settings)
    options_by_id = {option.id: option for option in options}

    selected_id = (model_id or "").strip().lower()
    if not selected_id:
        selected = options_by_id.get(settings.llm_provider)
    else:
        selected = options_by_id.get(selected_id)
        if selected is None:
            raise ValueError(f"Modelo no soportado: '{model_id}'.")

    if selected is None:
        raise ValueError("No hay modelos configurados para el chatbot.")

    if not selected.available:
        env_key = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
        }.get(selected.provider, "API_KEY")
        raise ValueError(
            f"El modelo seleccionado ({selected.label}) no está disponible: falta {env_key} en .env."
        )

    return selected


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on", "si", "sí"}


def _env_int(
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if minimum is not None:
        min_value = minimum
    if maximum is not None:
        max_value = maximum
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw is not None else default
    except Exception:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_float(
    name: str,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if minimum is not None:
        min_value = minimum
    if maximum is not None:
        max_value = maximum
    raw = os.getenv(name)
    try:
        value = float(str(raw).strip()) if raw is not None else default
    except Exception:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_choice(name: str, choices: set[str] | tuple[str, ...] | list[str], default: str) -> str:
    allowed = {choice.strip().lower() for choice in choices}
    value = (os.getenv(name) or default).strip().lower()
    return value if value in allowed else default


def get_settings() -> Settings:
    load_env()
    return Settings(
        llm_provider=_env_choice("LLM_PROVIDER", {"openai", "gemini", "groq"}, "openai"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        default_user_id=os.getenv("DEFAULT_USER_ID"),
        openai_timeout_seconds=_env_int("OPENAI_TIMEOUT_SECONDS", 25, min_value=5),
        ai_llm_retries=_env_int("AI_LLM_RETRIES", 1, min_value=0),
        deep_search_enabled=_env_bool("DEEP_SEARCH_ENABLED", False),
        deep_search_provider=_env_choice("DEEP_SEARCH_PROVIDER", {"tavily", "serper", "brave"}, "tavily"),
        deep_search_api_key=os.getenv("DEEP_SEARCH_API_KEY"),
        deep_search_max_results=_env_int("DEEP_SEARCH_MAX_RESULTS", 5, min_value=1, max_value=20),
        deep_search_timeout_seconds=_env_int("DEEP_SEARCH_TIMEOUT_SECONDS", 10, min_value=1, max_value=60),
        deep_search_max_sources=_env_int("DEEP_SEARCH_MAX_SOURCES", 5, min_value=1, max_value=20),
        deep_search_mode_default=_env_choice("DEEP_SEARCH_MODE_DEFAULT", {"auto", "on", "off"}, "auto"),
        deep_research_max_iterations=_env_int("DEEP_RESEARCH_MAX_ITERATIONS", 2, min_value=1, max_value=10),
        deep_research_max_tasks=_env_int("DEEP_RESEARCH_MAX_TASKS", 2, min_value=1, max_value=10),
        deep_research_max_queries_per_task=_env_int(
            "DEEP_RESEARCH_MAX_QUERIES_PER_TASK", 2, min_value=1, max_value=10
        ),
        deep_research_quality_threshold=_env_float(
            "DEEP_RESEARCH_QUALITY_THRESHOLD", 0.5, min_value=0.0, max_value=1.0
        ),
        deep_research_stagnation_limit=_env_int("DEEP_RESEARCH_STAGNATION_LIMIT", 2, min_value=1, max_value=10),
        deep_research_loop_repeat_limit=_env_int("DEEP_RESEARCH_LOOP_REPEAT_LIMIT", 1, min_value=1, max_value=10),
        deep_research_max_report_sources=_env_int("DEEP_RESEARCH_MAX_REPORT_SOURCES", 3, min_value=1, max_value=20),
        deep_research_internal_source_limit=_env_int(
            "DEEP_RESEARCH_INTERNAL_SOURCE_LIMIT", 3, min_value=1, max_value=20
        ),
        deep_research_parallel_queries=_env_bool("DEEP_RESEARCH_PARALLEL_QUERIES", False),
    )


def get_deep_search_config(settings: Optional[Settings] = None) -> DeepSearchConfig:
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


def get_deep_search_runtime_config(settings: Optional[Settings] = None) -> DeepSearchRuntimeConfig:
    current = settings or get_settings()
    return DeepSearchRuntimeConfig(
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


def get_deep_research_runtime_config(settings: Optional[Settings] = None):
    from ai.deep_research.types import DeepResearchRuntimeConfig as CanonicalRuntimeConfig

    current = settings or get_settings()
    return CanonicalRuntimeConfig(
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


def build_llm(model: str | None = None, provider: str | None = None, api_key: str | None = None):
    settings = get_settings()
    selected = resolve_chat_model(settings, provider or settings.llm_provider)
    provider_name = selected.provider
    model_name = model or selected.model
    key = api_key if api_key is not None else selected.api_key

    if provider_name == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=key,
            timeout=settings.openai_timeout_seconds,
            temperature=1,
        )

    if provider_name == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_name, google_api_key=key)

    if provider_name == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model_name, api_key=key)

    raise ValueError(f"Proveedor de modelo no soportado: '{provider_name}'.")
