from flask import Flask, render_template, url_for
from database.mongo_conn import init_app, mongo
from controllers.task_controller import task_bp, get_all_tasks_from_db

app = Flask(__name__)
init_app(app)

app.register_blueprint(task_bp)

def test_connection():
    try:
        mongo.db.command("ping")
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
