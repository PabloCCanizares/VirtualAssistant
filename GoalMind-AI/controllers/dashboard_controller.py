from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard_bp", __name__)


@dashboard_bp.route("/")
def dashboard():
    # La sincronización ahora se ejecuta en background via APScheduler (ver database/scheduler.py)
    return render_template("dashboard.html", page="dashboard")


@dashboard_bp.route("/agenda")
def agenda():
    return render_template("dashboard.html", page="agenda")


@dashboard_bp.route("/objetivos")
def objetivos():
    return render_template("dashboard.html", page="objetivos")


@dashboard_bp.route("/tareas")
def tareas():
    return render_template("dashboard.html", page="tareas")


@dashboard_bp.route("/estadisticas")
def estadisticas():
    return render_template("dashboard.html", page="estadisticas")


@dashboard_bp.route("/config")
def config():
    return render_template("dashboard.html", page="config")