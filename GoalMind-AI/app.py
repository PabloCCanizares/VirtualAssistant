from flask import Flask, render_template, url_for
from database.mongo_conn import get_collection, init_app, mongo, sync_from_remote
from controllers.task_controller import task_bp, get_all_tasks_from_db
from controllers.goal_controller import goal_bp
from controllers.event_controller import event_bp

app = Flask(__name__)
local, remote = init_app(app)
app.mongo_local = local
app.mongo_remote = remote

app.register_blueprint(task_bp)
app.register_blueprint(goal_bp)
app.register_blueprint(event_bp)

def sync_all_collections():
    if not remote:
        print("⚠️ No hay conexión remota → no se sincronizan datos.")
        return
    for col in ["tasks", "goals", "events"]:
        local_col, remote_col = get_collection(col)
        for doc in remote_col.find():
            sync_from_remote(col, doc)

@app.before_first_request
def on_startup():
    sync_all_collections()

def test_connection():
    try:
        local.db.command("ping")
        print(f"Tareas recibidas: {get_all_tasks_from_db()}")
        print("✅ Conectado correctamente a MongoDB Atlas")
    except Exception as e:
        print(f"❌ Error de conexión a MongoDB: {e}")
    
 
        
@app.route("/")
def dashboard():
    test_connection()
    return render_template("dashboard.html", page="dashboard")

@app.route("/agenda")
def agenda():
    # Reuse layout; you can create a dedicated template later.
    return render_template("dashboard.html", page="agenda")

@app.route("/objetivos")
def objetivos():
    return render_template("dashboard.html", page="objetivos")

@app.route("/tareas")
def tareas():
    return render_template("dashboard.html", page="tareas")

@app.route("/estadisticas")
def estadisticas():
    return render_template("dashboard.html", page="estadisticas")

@app.route("/config")
def config():
    return render_template("dashboard.html", page="config")

if __name__ == "__main__":
    app.run(debug=True)
