from pathlib import Path
import sys
from datetime import datetime

#Carga variables de entorno desde .env si existe
from dotenv import load_dotenv
#Modulo estandar de python para generar tokens seguros
import secrets
import os
#Importacion de la funcion init_app para realizar la conexion con la base de datos MongoDB (Local y Remota)
from database.mongo_conn import init_app, get_app_user_id
#Importacion del scheduler para sincronización en background
try:
    from database.scheduler import init_scheduler
except Exception as exc:
    init_scheduler = None
    print(f"⚠️ Scheduler deshabilitado (APScheduler no disponible): {exc}")
################ Aplicacion Flask ##################
env_root = Path(__file__).resolve().parent
# 1. Cargar .env de la raíz (fuente de verdad)
load_dotenv(env_root / ".env")
# 2. Fallback: GoalMind-AI/.env sin sobreescribir (variables de IA específicas)
ai_root = env_root / "GoalMind-AI"
if ai_root.exists():
    sys.path.insert(0, str(ai_root))
    ai_env = ai_root / ".env"
    if ai_env.exists():
        load_dotenv(ai_env, override=False)

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
