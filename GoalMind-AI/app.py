#Clase principal de la aplicacion para crear la aplicacion en Flask
from flask import Flask
#Modulo estandar de python para generar tokens seguros
import secrets
import os
#Importacion de la funcion init_app para realizar la conexion con la base de datos MongoDB (Local y Remota)
from database.mongo_conn import init_app
#Importacion del scheduler para sincronización en background
from database.scheduler import init_scheduler
#Importacion de los blueprints de los controladores
## Un blueprint es una forma de organizar un grupo relacionado de rutas y funcionalidades ##
from controllers.task_controller import task_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.goal_controller import goal_bp
from controllers.calendar_controller import calendar_bp
from controllers.stats_controller import stats_bp

################ Aplicacion Flask ##################
app = Flask(__name__)

################## Configuracion de la aplicacion ##################
# 1. Configuracion de la clave secreta para sesiones y seguridad
app.secret_key = secrets.token_hex(32)
# 2. Configuracion de la base de datos MongoDB (Local y Remota)
local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote
# 3. Activar y registrar los blueprints
app.register_blueprint(task_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(goal_bp) 
app.register_blueprint(calendar_bp) 
app.register_blueprint(stats_bp)

################ Inicialización del Scheduler ##################
# Solo inicializar si no estamos en el proceso de recarga de Flask (evita duplicados en modo debug)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    # Sincronización automática cada minuto
    init_scheduler(app, sync_interval_minutes=1)

################ Ejecucion de la aplicacion ##################
## La aplicacion se ejecuta solo si este archivo es el principal (python app.py), si se importa no se ejecuta ##
if __name__ == "__main__":
    app.run(debug=True) ## Modo debug activado para desarrollo, eliminar debug=True en produccion ##