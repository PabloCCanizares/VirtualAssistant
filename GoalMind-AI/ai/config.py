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
    openai_api_key: Optional[str]
    openai_model: str
    gemini_api_key: Optional[str]
    gemini_model: str
    groq_api_key: Optional[str]
    groq_model: str
    default_user_id: Optional[str]
    openai_timeout_seconds: int
    ai_llm_retries: int


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
        selected = next((option for option in options if option.available), options[0] if options else None)
    else:
        selected = options_by_id.get(selected_id)
        if selected is None:
            raise ValueError(f"Modelo no soportado: '{model_id}'.")

    if selected is None:
        raise ValueError("No hay modelos configurados para el chatbot.")

    if not selected.available:
        raise ValueError(
            f"El modelo seleccionado ({selected.label}) no está disponible: falta API key en .env."
        )

    return selected


def get_settings() -> Settings:
    load_env()
    timeout_raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "25")
    retries_raw = os.getenv("AI_LLM_RETRIES", "1")
    try:
        timeout_seconds = max(5, int(timeout_raw))
    except Exception:
        timeout_seconds = 25
    try:
        llm_retries = max(0, int(retries_raw))
    except Exception:
        llm_retries = 1
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        default_user_id=os.getenv("DEFAULT_USER_ID"),
        openai_timeout_seconds=timeout_seconds,
        ai_llm_retries=llm_retries,
    )
