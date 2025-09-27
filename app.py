from flask import Flask, render_template, url_for

app = Flask(__name__)

@app.route("/")
def dashboard():
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
