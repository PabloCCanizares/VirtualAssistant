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
    ai_provider: str
    openai_api_key: Optional[str]
    openai_model: str
    groq_api_key: Optional[str]
    groq_model: str
    default_user_id: Optional[str]
    openai_timeout_seconds: int
    ai_llm_retries: int


def get_settings() -> Settings:
    load_env()
    ai_provider = (os.getenv("AI_PROVIDER", "openai") or "openai").strip().lower()
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
        ai_provider=ai_provider,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        default_user_id=os.getenv("DEFAULT_USER_ID"),
        openai_timeout_seconds=timeout_seconds,
        ai_llm_retries=llm_retries,
    )
