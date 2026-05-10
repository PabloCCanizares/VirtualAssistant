import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_env(base_dir: Path) -> None:
    env_file = base_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        return

    message = (
        f"!! == Error: \nNo encontrado el archivo de entorno requerido: \n{env_file} \n "
        "Comprueba la ruta y asegurate de que el archivo '.env' existe en la raiz del proyecto. \n== !! "
    )
    logging.getLogger(__name__).error(message)
    raise RuntimeError(message)


def env_int(name: str, default: int = 1, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)
