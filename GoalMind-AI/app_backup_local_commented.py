# === Importacion de librerias necesarias para la aplicacion ===
from datetime import datetime # Manipulacion de fechas y horas
from pathlib import Path # Manipulacion de rutas de archivos y directorios
import logging # Configuracion de logs
import os # Interaccion con el sistema operativo
import secrets # Generacion tokens seguros
import sys # Manipulacion de argumentos y variables de entorno (.env)
# ··· Importacion de funciones ···
from dotenv import load_dotenv # Carga variables de entorno desde .env
from database.mongo_conn import init_app, get_app_user_id
from database.scheduler import init_scheduler


def load_project_env(base_dir: Path) -> None:
    """Carga variables de entorno desde el .env de la raíz del proyecto."""
    env_file = base_dir / ".env"

    if env_file.exists():
        load_dotenv(env_file)
        return

    print("⚠️ No existe .env en la raíz del proyecto. Se usarán variables del entorno del sistema.")
    load_dotenv()


################ Aplicacion Flask ##################
env_root = Path(__file__).resolve().parent

# 1. Cargar variables de entorno desde .env (fuente de verdad)
load_project_env(env_root)


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
    except Exception:
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


logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 2. Mantener path del submódulo de IA para imports
ai_root = env_root / "GoalMind-AI"
if ai_root.exists():
    sys.path.insert(0, str(ai_root))

#Clase principal de la aplicacion para crear la aplicacion en Flask
from flask import Flask

#Importacion de los blueprints de los controladores
## Un blueprint es una forma de organizar un grupo relacionado de rutas y funcionalidades ##
from controllers.ai_chat_controller import ai_chat_bp
from controllers.calendar_controller import calendar_bp
from controllers.category_controller import category_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.goal_controller import goal_bp
from controllers.project_controller import project_bp
from controllers.stats_controller import stats_bp
from controllers.task_controller import task_bp
from controllers.upload_controller import upload_bp
from model.category_model import CategoryModel

app = Flask(__name__)

################## Configuracion de la aplicacion ##################
# 1. Configuracion de la clave secreta para sesiones y seguridad
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
# 2. Configuracion de la base de datos MongoDB (Local y Remota)
local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote
# 3. Configuracion de almacenamiento local de documentos
upload_root_value = os.getenv("UPLOAD_ROOT", "uploads").strip()
upload_root = Path(upload_root_value)
if not upload_root.is_absolute():
    upload_root = Path(__file__).resolve().parent / upload_root
app.config["UPLOAD_ROOT"] = str(upload_root)
Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)
allowed_ext_env = os.getenv("UPLOAD_ALLOWED_EXTENSIONS", "").strip()
if allowed_ext_env:
    allowed_ext = {ext.strip().lower() for ext in allowed_ext_env.split(",") if ext.strip()}
else:
    allowed_ext = {
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
app.config["UPLOAD_ALLOWED_EXTENSIONS"] = allowed_ext
app.config["MAX_CONTENT_LENGTH"] = _env_int("MAX_CONTENT_LENGTH_MB", 25, minimum=1) * 1024 * 1024

# 4. Activar y registrar los blueprints
app.register_blueprint(task_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(goal_bp)
app.register_blueprint(project_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(category_bp)
app.register_blueprint(ai_chat_bp)

################ Context Processor - Variables globales para templates ##################
@app.context_processor
def inject_now():
    """Inyecta la funcion now() en todas las plantillas Jinja2."""
    sidebar_categories = []
    try:
        categories = CategoryModel.get_all_categories(usuario_id=get_app_user_id())
        sidebar_categories = [
            {"_id": str(c["_id"]), "name": c.get("name", "")}
            for c in categories
        ]
    except Exception:
        sidebar_categories = []
    return {
        "now": datetime.now,
        "sidebar_categories": sidebar_categories,
    }

################ Inicialización del Scheduler ##################
def setup_scheduler(flask_app):
    sync_interval = _env_int("SYNC_INTERVAL_MINUTES", 1, minimum=1)
    debug_enabled = _is_debug_enabled()

    if not _should_start_scheduler_process(debug_enabled):
        logger.info("Scheduler no iniciado en el proceso de recarga de Flask.")
        return

    # Scheduler crítico: si falla, el arranque debe abortar.
    init_scheduler(flask_app, sync_interval_minutes=sync_interval)


setup_scheduler(app)

################ Ejecucion de la aplicacion ##################
## La aplicacion se ejecuta solo si este archivo es el principal (python app.py), si se importa no se ejecuta ##
if __name__ == "__main__":
    app.run(debug=_is_debug_enabled()) ## Modo debug configurable por entorno ##
