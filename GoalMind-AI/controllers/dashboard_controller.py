from flask import Blueprint, jsonify, render_template, request

from database.mongo_conn import get_app_user_id
from services.dashboard_briefing_service import build_dashboard_briefing
from services.weekly_planning_service import (
    answer_weekly_planning_question,
    build_weekly_plan,
    get_current_week_plan,
    should_start_weekly_planning,
    start_weekly_planning_session,
)

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


@dashboard_bp.route("/api/dashboard/briefing")
def dashboard_briefing():
    briefing = build_dashboard_briefing(usuario_id=str(get_app_user_id()))
    return jsonify(briefing)


@dashboard_bp.route("/api/planning/weekly/should-start")
def weekly_planning_should_start():
    return jsonify(should_start_weekly_planning(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/current")
def weekly_planning_current():
    return jsonify(get_current_week_plan(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/start", methods=["POST"])
def weekly_planning_start():
    return jsonify(start_weekly_planning_session(usuario_id=str(get_app_user_id())))


@dashboard_bp.route("/api/planning/weekly/<session_id>/answer", methods=["POST"])
def weekly_planning_answer(session_id):
    payload = request.get_json(silent=True) or {}
    field = payload.get("field")
    value = payload.get("value")
    try:
        result = answer_weekly_planning_question(
            session_id=session_id,
            field=field,
            value=value,
            usuario_id=str(get_app_user_id()),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **result})


@dashboard_bp.route("/api/planning/weekly/<session_id>/plan", methods=["POST"])
def weekly_planning_build_plan(session_id):
    try:
        result = build_weekly_plan(session_id=session_id, usuario_id=str(get_app_user_id()))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **result})
