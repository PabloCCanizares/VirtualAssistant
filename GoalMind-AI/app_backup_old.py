
# === Importacion de librerias necesarias para la aplicacion ===
from pathlib import Path # Manipulacion de rutas de archivos y directorios
from datetime import datetime # Manipulacion de fechas y horas
import secrets # Generacion tokens seguros
import os # Interaccion con el sistema operativo
import sys # Manipulacion de argumentos y variables de entorno (.env)
# ··· Importacion de funciones ···
from dotenv import load_dotenv # Carga variables de entorno desde .env
from database.mongo_conn import init_app, get_app_user_id

#Importacion del scheduler para sincronización en background
try:
    from database.scheduler import init_scheduler
except Exception as exc:
    init_scheduler = None
    print(f"Error con init_scheduler en database/scheduler.py: {exc}")

################ Aplicacion Flask ##################
env_root = Path(__file__).resolve().parent


def load_project_env(base_dir: Path) -> None:
    """Carga variables de entorno desde el .env de la raíz del proyecto."""
    env_file = base_dir / ".env"

    if env_file.exists():
        load_dotenv(env_file)
        return

    print("⚠️ No existe .env en la raíz del proyecto. Se usarán variables del entorno del sistema.")
    load_dotenv()


# 1. Cargar variables de entorno desde .env (fuente de verdad)
load_project_env(env_root)
# 2. Mantener path del submódulo de IA para imports
ai_root = env_root / "GoalMind-AI"
if ai_root.exists():
    sys.path.insert(0, str(ai_root))

#Clase principal de la aplicacion para crear la aplicacion en Flask
from flask import Flask

#Importacion de los blueprints de los controladores
## Un blueprint es una forma de organizar un grupo relacionado de rutas y funcionalidades ##
from controllers.task_controller import task_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.goal_controller import goal_bp
from controllers.project_controller import project_bp
from controllers.calendar_controller import calendar_bp
from controllers.stats_controller import stats_bp
from controllers.upload_controller import upload_bp
from controllers.category_controller import category_bp
from controllers.ai_chat_controller import ai_chat_bp
from model.category_model import CategoryModel

app = Flask(__name__)

################## Configuracion de la aplicacion ##################
# 1. Configuracion de la clave secreta para sesiones y seguridad
app.secret_key = secrets.token_hex(32)
# 2. Configuracion de la base de datos MongoDB (Local y Remota)
local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote
# 3. Configuracion de almacenamiento local de documentos
app.config["UPLOAD_ROOT"] = str(Path(__file__).resolve().parent / "uploads")
Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)
app.config["UPLOAD_ALLOWED_EXTENSIONS"] = {
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
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

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
# Solo inicializar si no estamos en el proceso de recarga de Flask (evita duplicados en modo debug)
if init_scheduler and (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug):
    # Sincronización automática cada minuto
    init_scheduler(app, sync_interval_minutes=1)

################ Ejecucion de la aplicacion ##################
## La aplicacion se ejecuta solo si este archivo es el principal (python app.py), si se importa no se ejecuta ##
if __name__ == "__main__":
    app.run(debug=True) ## Modo debug activado para desarrollo, eliminar debug=True en produccion ##
