"""Bateria del controlador del dashboard.

Las seis rutas solo renderizan la misma plantilla con un parametro `page`
distinto. Aqui se verifica que cada una responde 200 y pasa el `page`
correcto al template.
"""

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
    app.register_blueprint(dashboard_bp)
    client = app.test_client()
    client.captured = captured
    return client


@pytest.mark.parametrize(
    "url,expected_page",
    [
        ("/", "dashboard"),
        ("/agenda", "agenda"),
        ("/objetivos", "objetivos"),
        ("/tareas", "tareas"),
        ("/estadisticas", "estadisticas"),
        ("/config", "config"),
    ],
)
def test_each_dashboard_route(client, url, expected_page):
    resp = client.get(url)
    assert resp.status_code == 200
    assert client.captured[-1]["template"] == "dashboard.html"
    assert client.captured[-1]["page"] == expected_page


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

    answers = [
        ("weekly_available_hours", "3"),
        ("current_energy", "alta"),
        ("weekly_top_priorities", "Preparar"),
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
