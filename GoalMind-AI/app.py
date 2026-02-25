# === Importacion de librerias necesarias para la aplicacion ===
import logging # Manipulacion de logs
import os # Manipulacion del entorno .env para interaccion con el sistema operativo
import secrets # Generacion tokens seguros
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv # Carga variables de entorno desde .env
from flask import Flask
# ··· Importacion de funciones ···
from database.mongo_conn import get_app_user_id, init_app
from database.scheduler import init_scheduler
from model.category_model import CategoryModel

# === Configuración de constantes y funciones de utilidad ===
DEFAULT_UPLOAD_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "png",
    "jpg",
    "jpeg",
    "csv",
    "xlsx",
    "pptx",
    "zip",
}

def load_project_env(base_dir: Path) -> None:
    """Carga variables de entorno.

    Args:
        base_dir: Ruta (Path) base donde se busca el archivo '.env', es decir, la raiz del proyecto.

    Returns:
        None.

    Raises:
        RuntimeError: Si no se encuentra '.env'. Es un error crítico porque falta API_KEY y URLs de MongoDB.
    """

    env_file = base_dir / ".env" # Operador '/' de Path, sirve para concatenar rutas.

    if env_file.exists():
        load_dotenv(env_file)
        return
    
    message = (
        f"!! == Error: \nNo encontrado el archivo de entorno requerido: \n{env_file} \n "
        "Comprueba la ruta y asegurate de que el archivo '.env' existe en la raíz del proyecto. \n== !! "
    )
    logging.getLogger(__name__).error(message)
    raise RuntimeError(message)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}

def _env_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)

def _is_production() -> bool:
    return os.getenv("FLASK_ENV", "development").strip().lower() == "production"

def _is_debug_enabled() -> bool:
    return _env_bool("FLASK_DEBUG", not _is_production())

def _should_start_scheduler_process(debug_enabled: bool) -> bool:
    # Con reloader activo, solo iniciar en el proceso hijo real.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return True
    return not debug_enabled

def _configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger(__name__)

def _configure_upload_settings(flask_app: Flask) -> None:
    upload_root_value = os.getenv("UPLOAD_ROOT", "uploads").strip()
    upload_root = Path(upload_root_value)
    if not upload_root.is_absolute():
        upload_root = Path(__file__).resolve().parent / upload_root

    flask_app.config["UPLOAD_ROOT"] = str(upload_root)
    Path(flask_app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)

    allowed_ext_env = os.getenv("UPLOAD_ALLOWED_EXTENSIONS", "").strip()
    if allowed_ext_env:
        allowed_ext = {
            ext.strip().lower() for ext in allowed_ext_env.split(",") if ext.strip()
        }
    else:
        allowed_ext = set(DEFAULT_UPLOAD_EXTENSIONS)

    flask_app.config["UPLOAD_ALLOWED_EXTENSIONS"] = allowed_ext
    flask_app.config["MAX_CONTENT_LENGTH"] = (
        _env_int("MAX_CONTENT_LENGTH_MB", 25, minimum=1) * 1024 * 1024
    )

def _register_blueprints(flask_app: Flask) -> None:
    # Importación de blueprints
    from controllers.ai_chat_controller import ai_chat_bp
    from controllers.calendar_controller import calendar_bp
    from controllers.category_controller import category_bp
    from controllers.dashboard_controller import dashboard_bp
    from controllers.goal_controller import goal_bp
    from controllers.project_controller import project_bp
    from controllers.stats_controller import stats_bp
    from controllers.task_controller import task_bp
    from controllers.upload_controller import upload_bp

    flask_app.register_blueprint(task_bp)
    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(goal_bp)
    flask_app.register_blueprint(project_bp)
    flask_app.register_blueprint(calendar_bp)
    flask_app.register_blueprint(stats_bp)
    flask_app.register_blueprint(upload_bp)
    flask_app.register_blueprint(category_bp)
    flask_app.register_blueprint(ai_chat_bp)

def setup_scheduler(flask_app: Flask, logger: logging.Logger) -> None:
    sync_interval = _env_int("SYNC_INTERVAL_MINUTES", 1, minimum=1)
    debug_enabled = _is_debug_enabled()

    if not _should_start_scheduler_process(debug_enabled):
        logger.info("Scheduler no iniciado en el proceso de recarga de Flask.")
        return

    # Scheduler crítico: si falla, el arranque debe abortar.
    init_scheduler(flask_app, sync_interval_minutes=sync_interval)


# === Inicialización de entorno y logging ===
env_root = Path(__file__).resolve().parent
load_project_env(env_root)
logger = _configure_logging()

# === Construcción de la app ===
app = Flask(__name__)
if _is_production():
    production_secret = os.getenv("FLASK_SECRET_KEY")
    if not production_secret:
        logger.error(
            "FLASK_SECRET_KEY no está definido y FLASK_ENV=production. "
            "El arranque se detiene por seguridad."
        )
        raise RuntimeError(
            "Falta FLASK_SECRET_KEY en producción. Define la variable en '.env'."
        )
    app.secret_key = production_secret
else:
    app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote

_configure_upload_settings(app)
_register_blueprints(app)


# === Context processor global ===
@app.context_processor
def inject_now():
    """Inyecta now() y categorías del sidebar en todas las plantillas."""
    sidebar_categories = []
    try:
        categories = CategoryModel.get_all_categories(usuario_id=get_app_user_id())
        sidebar_categories = [
            {"_id": str(category["_id"]), "name": category.get("name", "")}
            for category in categories
        ]
    except Exception:
        logger.warning(
            "No se pudieron cargar las categorías del sidebar.",
            exc_info=True,
        )
        sidebar_categories = []

    return {
        "now": datetime.now,
        "sidebar_categories": sidebar_categories,
    }


# === Scheduler en background ===
setup_scheduler(app, logger)


# === Ejecución de aplicación ===
if __name__ == "__main__":
    app.run(debug=_is_debug_enabled())
