from datetime import datetime, timedelta

from bson import ObjectId

from services.weekly_summary_service import build_weekly_summary_metrics

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def test_weekly_summary_metrics_reads_real_weekly_signals(mongo_mock):
    now = datetime(2026, 7, 3, 12, 0, 0)
    task_completed = ObjectId()
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {
                "_id": task_completed,
                "contenido": "Cerrada esta semana",
                "estado": "completada",
                "fecha_limite": now,
                "updated_at": now - timedelta(days=1),
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Pendiente hoy",
                "estado": "pendiente",
                "fecha_limite": now,
                "prioridad": "alta",
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Atrasada",
                "estado": "pendiente",
                "fecha_limite": now - timedelta(days=3),
                "usuario_id": USER_ID,
            },
        ]
    )
    mongo_mock.local_db["Events"].insert_many(
        [
            {
                "_id": ObjectId(),
                "titulo": "Bloque de foco",
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
            "mood_label": "bueno",
            "usuario_id": USER_ID,
        }
    )

    metrics = build_weekly_summary_metrics(usuario_id=USER_ID, now=now)

    assert metrics["tasks"]["completed_this_week"] == 1
    assert metrics["tasks"]["due_today"] == 1
    assert metrics["tasks"]["overdue"] == 1
    assert metrics["tasks"]["high_priority_pending"] == 1
    assert metrics["events"]["busy_hours_week"] == 12
    assert metrics["events"]["productive_hours_week"] == 2
    assert metrics["events"]["non_productive_hours_week"] == 10
    assert metrics["events"]["recovery_hours_week"] == 9
    assert metrics["events"]["focus_hours_week"] == 2
    assert metrics["events"]["focus_share"] == 100
    assert metrics["events"]["layer_hours_week"]["mantenimiento"] == 1
    assert metrics["events"]["layer_hours_week"]["salud"] == 1
    assert metrics["events"]["layer_hours_week"]["sueno"] == 8
    assert metrics["daily_metrics"]["avg_sleep_hours"] == 7.5
    assert metrics["daily_metrics"]["avg_mood_score"] == 4
    assert len(metrics["bars"]["completed_tasks"]) == 7
