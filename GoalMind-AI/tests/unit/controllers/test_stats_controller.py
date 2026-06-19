"""Bateria del controlador REST de estadisticas.

Cubre la unica ruta HTTP (`/<stat_name>`) y las cuatro funciones de
estadistica que despacha: tareas cumplidas del mes, progreso de proyectos,
relevancia de tareas y distribucion de eventos por tipo.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import Flask

from controllers import stats_controller
from controllers.stats_controller import stats_bp


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.config["TESTING"] = True

    def _fake_render(template_name, **ctx):
        keys = ",".join(sorted(ctx.keys()))
        return f"RENDER::{template_name}::{keys}"

    monkeypatch.setattr(stats_controller, "render_template", _fake_render)
    app.register_blueprint(stats_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Funciones puras de estadistica
# ---------------------------------------------------------------------------


class TestStatsFunctions:
    def test_tasks_completed_month_with_no_tasks(self, monkeypatch):
        monkeypatch.setattr(
            stats_controller.TaskModel, "get_all_tasks",
            staticmethod(lambda usuario_id=None: []),
        )
        out = stats_controller.stats_tasks_completed_month()
        assert out["total"] == 0
        assert out["completed"] == 0
        assert out["percentage_completed"] == 0.0

    def test_tasks_completed_month_with_data(self, monkeypatch):
        year = datetime.now(timezone.utc).year
        in_year = datetime(year, 6, 1, tzinfo=timezone.utc)
        out_of_year = datetime(year - 5, 6, 1, tzinfo=timezone.utc)
        tasks = [
            {"_id": "t1", "estado": "completada", "fecha_limite": in_year},
            {"_id": "t2", "estado": "pendiente", "fecha_limite": in_year},
            {"_id": "t3", "estado": "completada", "fecha_limite": out_of_year},
        ]
        monkeypatch.setattr(
            stats_controller.TaskModel, "get_all_tasks",
            staticmethod(lambda usuario_id=None: tasks),
        )
        out = stats_controller.stats_tasks_completed_month()
        # Solo cuentan las del anio actual.
        assert out["total"] == 2
        assert out["completed"] == 1
        assert out["percentage_completed"] == 50.0

    def test_projects_progress(self, monkeypatch):
        from bson import ObjectId
        pid = ObjectId()
        monkeypatch.setattr(
            stats_controller.ProjectModel, "get_all_projects",
            staticmethod(lambda usuario_id=None: [{"_id": pid, "titulo": "P"}]),
        )
        monkeypatch.setattr(
            stats_controller.GoalModel, "get_by_project",
            staticmethod(lambda pid_, usuario_id=None: [{"progreso": 80}, {"progreso": 40}]),
        )
        monkeypatch.setattr(
            stats_controller.ProjectModel, "calculate_progress_from_goals",
            staticmethod(lambda goals: sum(g.get("progreso", 0) for g in goals) / max(len(goals), 1)),
        )
        out = stats_controller.stats_projects_progress()
        assert out["count"] == 1
        assert out["projects"][0]["titulo"] == "P"
        assert out["projects"][0]["progreso_medio"] == 60

    def test_tasks_relevance_month(self, monkeypatch):
        year = datetime.now(timezone.utc).year
        tasks = [
            {"_id": "1", "prioridad": "alta", "fecha_limite": datetime(year, 6, 1)},
            {"_id": "2", "prioridad": "media", "fecha_limite": datetime(year, 6, 2)},
            {"_id": "3", "prioridad": "baja", "fecha_limite": datetime(year - 1, 1, 1)},
        ]
        monkeypatch.setattr(
            stats_controller.TaskModel, "get_all_tasks",
            staticmethod(lambda usuario_id=None: tasks),
        )
        out = stats_controller.stats_tasks_relevance_month()
        assert out["total_points"] == 3
        assert out["month_points"] == 2
        assert len(out["month_tasks"]) == 2

    def test_events_by_type_month(self, monkeypatch):
        monkeypatch.setattr(
            stats_controller.eventModel, "get_all_events",
            staticmethod(lambda usuario_id=None: [
                {"_id": "e1", "tipo_evento": "trabajo"},
                {"_id": "e2", "tipo_evento": "trabajo"},
                {"_id": "e3", "tipo_evento": "personal"},
                {"_id": "e4"},  # sin tipo
            ]),
        )
        out = stats_controller.stats_events_by_type_month()
        assert out["total"] == 4
        trabajo = next(d for d in out["distribution"] if d["tipo"] == "trabajo")
        assert trabajo["count"] == 2
        assert trabajo["percentage"] == 50.0


# ---------------------------------------------------------------------------
# Helpers de parseo de fechas
# ---------------------------------------------------------------------------


class TestDateHelpers:
    def test_parse_date_native_datetime(self):
        d = datetime.now(timezone.utc)
        assert stats_controller._parse_date(d) == d

    def test_parse_date_naive_assumed_utc(self):
        d = datetime(2026, 1, 1)
        out = stats_controller._parse_date(d)
        assert out.tzinfo is not None

    def test_parse_date_iso_string(self):
        out = stats_controller._parse_date("2026-01-01T00:00:00Z")
        assert out.year == 2026

    def test_parse_date_extended_json_with_ms(self):
        out = stats_controller._parse_date({"$date": 1700000000000})
        assert out is not None

    def test_parse_date_extended_json_iso(self):
        out = stats_controller._parse_date({"$date": "2026-01-01T00:00:00Z"})
        assert out.year == 2026

    def test_parse_date_none_or_invalid(self):
        assert stats_controller._parse_date(None) is None
        assert stats_controller._parse_date("not-a-date") is None
        assert stats_controller._parse_date(123) is None

    def test_date_to_iso(self):
        out = stats_controller._date_to_iso(datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert "2026-05-01" in out

    def test_is_in_ym_year_matches(self):
        assert stats_controller._is_in_ym(datetime(2026, 1, 1, tzinfo=timezone.utc), 2026) is True
        assert stats_controller._is_in_ym(datetime(2025, 12, 31, tzinfo=timezone.utc), 2026) is False


# ---------------------------------------------------------------------------
# Ruta /<stat_name>
# ---------------------------------------------------------------------------


class TestRenderStatBlock:
    def test_unknown_stat_returns_404(self, client):
        resp = client.get("/stats/unknown_stat")
        assert resp.status_code == 404

    def test_known_stat_returns_render(self, client, monkeypatch):
        monkeypatch.setattr(
            stats_controller.TaskModel, "get_all_tasks",
            staticmethod(lambda usuario_id=None: []),
        )
        resp = client.get("/stats/tasks_completed_month")
        assert resp.status_code == 200
        assert b"stat_tasks_completed_panel" in resp.data

    def test_stat_function_exception_returns_500(self, client, monkeypatch):
        def _boom(usuario_id=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            stats_controller.TaskModel, "get_all_tasks", staticmethod(_boom)
        )
        resp = client.get("/stats/tasks_completed_month")
        assert resp.status_code == 500
