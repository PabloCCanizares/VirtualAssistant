"""Bateria del controlador del dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from bson import ObjectId
from flask import Flask

from controllers import dashboard_controller
from controllers.dashboard_controller import dashboard_bp

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    captured: list[dict] = []

    def _fake_render(template_name, **ctx):
        captured.append({"template": template_name, **ctx})
        return f"RENDER::{template_name}::{ctx.get('page', '')}"

    monkeypatch.setattr(dashboard_controller, "render_template", _fake_render)
    app.add_url_rule("/calendar", endpoint="calendar_bp.calendar_page", view_func=lambda: "calendar")
    app.add_url_rule("/projects", endpoint="project_bp.list_projects", view_func=lambda: "projects")
    app.add_url_rule("/projects/<project_id>", endpoint="project_bp.view_project", view_func=lambda project_id: project_id)
    app.add_url_rule("/goals", endpoint="goal_bp.list_goals", view_func=lambda: "goals")
    app.add_url_rule("/goals/<goal_id>", endpoint="goal_bp.view_goal", view_func=lambda goal_id: goal_id)
    app.add_url_rule("/tasks", endpoint="task_bp.list_tasks_by_user", view_func=lambda: "tasks")
    app.add_url_rule("/tasks/<task_id>", endpoint="task_bp.view_task", view_func=lambda task_id: task_id)
    app.register_blueprint(dashboard_bp)
    client = app.test_client()
    client.captured = captured
    return client


@pytest.mark.parametrize(
    "url,expected_page,expected_template",
    [
        ("/", "dashboard", "dashboard.html"),
        ("/reunion-semanal", "dashboard", "weekly_meeting.html"),
        ("/agenda", "agenda", "dashboard.html"),
        ("/objetivos", "objetivos", "dashboard.html"),
        ("/tareas", "tareas", "dashboard.html"),
        ("/estadisticas", "estadisticas", "statistics.html"),
        ("/config", "config", "config.html"),
    ],
)
def test_each_dashboard_route(client, url, expected_page, expected_template):
    resp = client.get(url)
    assert resp.status_code == 200
    assert client.captured[-1]["template"] == expected_template
    assert client.captured[-1]["page"] == expected_page


def test_dashboard_uses_weekly_metrics_for_summary_cards(client, mongo_mock, monkeypatch):
    monkeypatch.setattr(dashboard_controller, "DEFAULT_USER_ID", USER_ID)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Cerrada",
            "fecha_limite": now,
            "updated_at": now,
            "estado": "completada",
            "usuario_id": USER_ID,
        }
    )
    mongo_mock.local_db["Events"].insert_many(
        [
            {
                "_id": ObjectId(),
                "titulo": "Bloque foco",
                "tipo_evento": "foco",
                "capa_tiempo": "productivo",
                "fecha_inicio": now.replace(hour=9),
                "fecha_fin": now.replace(hour=11),
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "titulo": "Dormir",
                "tipo_evento": "sueno",
                "fecha_inicio": now.replace(hour=0),
                "fecha_fin": now.replace(hour=8),
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "titulo": "Deporte",
                "tipo_evento": "deporte",
                "fecha_inicio": now.replace(hour=12),
                "fecha_fin": now.replace(hour=13),
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "titulo": "Comida",
                "tipo_evento": "comida",
                "fecha_inicio": now.replace(hour=14),
                "fecha_fin": now.replace(hour=15),
                "usuario_id": USER_ID,
            },
        ]
    )
    mongo_mock.local_db["DailyMetrics"].insert_one(
        {
            "_id": ObjectId(),
            "date": now.date().isoformat(),
            "sleep_hours": 7.5,
            "mood_score": 4,
            "usuario_id": USER_ID,
        }
    )

    resp = client.get("/")
    dashboard = client.captured[-1]["dashboard"]
    cards = {card["label"]: card for card in dashboard["summary_cards"]}
    stats = {stat["label"]: stat for stat in dashboard["stats"]}

    assert resp.status_code == 200
    assert cards["Foco"]["value"] == "2h"
    assert cards["Carga"]["value"] == "5%"
    assert cards["Carga"]["subdetail"] == "2h productivas"
    assert cards["No productivo"]["value"] == "10h"
    assert "Sueno" not in cards
    assert len(cards["Foco"]["bars"]) == 7
    assert len(cards["Carga"]["bars"]) == 7
    assert stats["Carga productiva"]["value"] == "5%"
    assert stats["Tiempo separado"]["value"] == "10h"
    assert stats["Tareas completadas"]["value"] == "1"
    assert dashboard["weekly_metrics"]["events"]["productive_hours_week"] == 2
    assert dashboard["weekly_metrics"]["daily_metrics"]["avg_mood_score"] == 4

    api_resp = client.get("/api/dashboard/summary")
    payload = api_resp.get_json()
    api_cards = {card["label"]: card for card in payload["summary_cards"]}
    api_stats = {stat["label"]: stat for stat in payload["stats"]}

    assert api_resp.status_code == 200
    assert api_cards["Carga"]["value"] == "5%"
    assert api_cards["Carga"]["subdetail"] == "2h productivas"
    assert api_stats["Carga productiva"]["value"] == "5%"
    assert payload["weekly_metrics"]["events"]["productive_hours_week"] == 2


def test_dashboard_ignores_paused_projects_goals_and_tasks(client, mongo_mock, monkeypatch):
    monkeypatch.setattr(dashboard_controller, "DEFAULT_USER_ID", USER_ID)
    now = datetime.now()
    active_project_id = ObjectId()
    paused_project_id = ObjectId()
    active_goal_id = ObjectId()
    paused_goal_id = ObjectId()
    goal_in_paused_project_id = ObjectId()

    mongo_mock.local_db["Projects"].insert_many(
        [
            {"_id": active_project_id, "titulo": "Proyecto visible", "estado": "activo", "usuario_id": USER_ID},
            {"_id": paused_project_id, "titulo": "Proyecto pausado", "estado": "pausado", "usuario_id": USER_ID},
        ]
    )
    mongo_mock.local_db["Goals"].insert_many(
        [
            {
                "_id": active_goal_id,
                "titulo": "Objetivo visible",
                "estado": "en progreso",
                "project_id": active_project_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": paused_goal_id,
                "titulo": "Objetivo pausado",
                "estado": "en pausa",
                "project_id": active_project_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": goal_in_paused_project_id,
                "titulo": "Objetivo de proyecto pausado",
                "estado": "en progreso",
                "project_id": paused_project_id,
                "usuario_id": USER_ID,
            },
        ]
    )
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {
                "_id": ObjectId(),
                "contenido": "Tarea visible",
                "estado": "pendiente",
                "prioridad": "alta",
                "fecha_limite": now - timedelta(days=1),
                "objetivo_id": active_goal_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Tarea de objetivo pausado",
                "estado": "pendiente",
                "prioridad": "alta",
                "fecha_limite": now - timedelta(days=1),
                "objetivo_id": paused_goal_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Tarea de proyecto pausado",
                "estado": "pendiente",
                "prioridad": "alta",
                "fecha_limite": now - timedelta(days=1),
                "project_id": paused_project_id,
                "usuario_id": USER_ID,
            },
        ]
    )

    resp = client.get("/")
    dashboard = client.captured[-1]["dashboard"]

    assert resp.status_code == 200
    assert [project["title"] for project in dashboard["projects"]] == ["Proyecto visible"]
    assert dashboard["projects"][0]["goals"] == 1
    assert [goal["title"] for goal in dashboard["goals"]] == ["Objetivo visible"]
    assert [task["title"] for task in dashboard["tasks"]] == ["Tarea visible"]


def test_dashboard_briefing_api_returns_mcp_work_items(client, mongo_mock):
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Vencida",
            "fecha_limite": datetime.utcnow() - timedelta(days=1),
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    resp = client.get("/api/dashboard/briefing")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["user_id"] == USER_ID
    assert payload["assistant_tasks"]
    assert "diagnosis" in payload
    assert "missing_context" in payload


def test_weekly_planning_api_flow(client, mongo_mock):
    task_id = ObjectId()
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": task_id,
            "contenido": "Preparar semana",
            "fecha_limite": datetime.utcnow() + timedelta(days=1),
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    start_resp = client.post("/api/planning/weekly/start")
    start_payload = start_resp.get_json()
    session_id = start_payload["session"]["_id"]

    assert start_resp.status_code == 200
    assert start_payload["created"] is True
    assert any(question["field"] == "available_windows" for question in start_payload["questions"])

    answers = [
        ("weekly_available_hours", "3"),
        ("current_energy", "alta"),
        ("weekly_top_priorities", "Preparar"),
        ("available_windows", "Lunes tarde\nMiercoles manana"),
        ("success_criteria", "Semana clara"),
    ]
    for field, value in answers:
        resp = client.post(
            f"/api/planning/weekly/{session_id}/answer",
            json={"field": field, "value": value},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    plan_resp = client.post(f"/api/planning/weekly/{session_id}/plan")
    plan_payload = plan_resp.get_json()

    assert plan_resp.status_code == 200
    assert plan_payload["success"] is True
    assert plan_payload["ready"] is True
    assert plan_payload["plan"]["focus"]["available_windows"] == ["Lunes tarde", "Miercoles manana"]
    assert any(item["task"]["_id"] == str(task_id) for item in plan_payload["plan"]["do_this_week"])


def test_weekly_meeting_can_run_through_mcp_bridge(client, mongo_mock):
    task_id = ObjectId()
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": task_id,
            "contenido": "Preparar reunion MCP",
            "fecha_limite": datetime.utcnow() + timedelta(days=1),
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    current_resp = client.get("/api/mcp/planning/weekly/current")
    current_payload = current_resp.get_json()
    start_resp = client.post("/api/mcp/planning/weekly/start")
    start_payload = start_resp.get_json()
    session_id = start_payload["session"]["_id"]

    assert current_resp.status_code == 200
    assert current_payload["source"] == "mcp"
    assert "get_current_week_plan" in current_payload["mcp_tools"]
    assert start_resp.status_code == 200
    assert start_payload["source"] == "mcp"
    assert "start_weekly_planning_session" in start_payload["mcp_tools"]

    answers = [
        ("weekly_available_hours", "4"),
        ("current_energy", "alta"),
        ("weekly_top_priorities", "Preparar"),
        ("success_criteria", "Reunion planificada"),
    ]
    for field, value in answers:
        resp = client.post(
            f"/api/mcp/planning/weekly/{session_id}/answer",
            json={"field": field, "value": value},
        )
        payload = resp.get_json()
        assert resp.status_code == 200
        assert payload["success"] is True
        assert payload["source"] == "mcp"

    plan_resp = client.post(f"/api/mcp/planning/weekly/{session_id}/plan")
    plan_payload = plan_resp.get_json()

    assert plan_resp.status_code == 200
    assert plan_payload["source"] == "mcp"
    assert plan_payload["ready"] is True
    assert any(item["task"]["_id"] == str(task_id) for item in plan_payload["plan"]["do_this_week"])


def test_weekly_planning_api_rejects_invalid_field(client):
    start_payload = client.post("/api/planning/weekly/start").get_json()
    session_id = start_payload["session"]["_id"]

    resp = client.post(
        f"/api/planning/weekly/{session_id}/answer",
        json={"field": "nope", "value": "x"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
