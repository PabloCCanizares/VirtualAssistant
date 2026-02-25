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
    default_user_id: Optional[str]


def get_settings() -> Settings:
    load_env()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano"),
        default_user_id=os.getenv("DEFAULT_USER_ID"),
    )
