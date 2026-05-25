"""Bateria del controlador del dashboard.

Las seis rutas solo renderizan la misma plantilla con un parametro `page`
distinto. Aqui se verifica que cada una responde 200 y pasa el `page`
correcto al template.
"""

from __future__ import annotations

import pytest
from flask import Flask

from controllers import dashboard_controller
from controllers.dashboard_controller import dashboard_bp


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
