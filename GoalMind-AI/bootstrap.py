# === Importacion de librerias necesarias para la aplicacion ===
import logging # Manipulacion de logs
import os # Manipulacion del entorno .env para interaccion con el sistema operativo
from pathlib import Path

from dotenv import load_dotenv # Carga variables de entorno desde .env


def load_project_env(base_dir: Path) -> None:
    """Carga variables de entorno.

    Args:
        base_dir: Ruta (Path) base donde se busca el archivo '.env', es decir, la raiz del proyecto.

    Returns:
        None.

    Raises:
        RuntimeError: Si no se encuentra '.env'. Es un error crítico porque falta API_KEY y URLs de MongoDB.
    """
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


def env_bool(name: str, default: bool = False) -> bool:
    """Leer variables de entorno (booleanos) de forma segura y consistente.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor por defecto si la variable no está definida.

    Returns:
        bool: Valor booleano interpretado de la variable de entorno. 
        (Solo es true si el valor sin espacios y en minúsculas es uno de los contenidos en el conjunto in{})
    """
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def env_int(name: str, default: int = 1, minimum: int = 1) -> int:
    """Leer variables de entorno (enteros) de forma segura y consistente.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor por defecto si la variable no está definida o no se puede parsear como entero.
        minimum: Valor mínimo permitido.

    Returns:
        int: Valor entero interpretado de la variable de entorno. 
    """
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def is_production() -> bool:
    """Indica si la app se ejecuta en modo produccion."""
    return os.getenv("FLASK_ENV", "development").strip().lower() == "production"


def is_debug_enabled() -> bool:
    """Calcula el flag debug de Flask segun entorno."""
    return env_bool("FLASK_DEBUG", not is_production())


def should_start_scheduler_process(debug_enabled: bool) -> bool:
    """Con reloader, inicia scheduler solo en el proceso hijo real."""
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return True
    return not debug_enabled


def configure_logging(logger_name: str) -> logging.Logger:
    """Configura logging global y devuelve logger del modulo."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger(logger_name)
