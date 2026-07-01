from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId

from mcp_server import tools

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


def test_get_active_user_uses_app_user_id(mongo_mock):
    out = tools.get_active_user()

    assert out["success"] is True
    assert out["user_id"] == USER_ID
    assert out["storage"]["local_db_configured"] is True
    assert out["storage"]["remote_db_configured"] is True


def test_list_projects_returns_only_active_user_projects(mongo_mock):
    mongo_mock.local_db["Projects"].insert_many(
        [
            {"_id": ObjectId(), "titulo": "Proyecto visible", "usuario_id": USER_ID},
            {"_id": ObjectId(), "titulo": "Proyecto ajeno", "usuario_id": "otro-user"},
        ]
    )

    out = tools.list_projects()

    assert out["success"] is True
    assert out["count"] == 1
    assert out["projects"][0]["titulo"] == "Proyecto visible"


def test_list_projects_searches_title_and_description(mongo_mock):
    mongo_mock.local_db["Projects"].insert_many(
        [
            {
                "_id": ObjectId(),
                "titulo": "Docencia",
                "descripcion": "Plan de clases",
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "titulo": "Investigacion",
                "descripcion": "Paper sobre agentes",
                "usuario_id": USER_ID,
            },
        ]
    )

    out = tools.list_projects(search="agentes")

    assert out["success"] is True
    assert out["count"] == 1
    assert out["projects"][0]["titulo"] == "Investigacion"


def test_get_user_snapshot_filters_active_user_and_serializes_dates(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    due_at = (datetime.utcnow() + timedelta(days=3)).replace(microsecond=0)
    mongo_mock.local_db["Projects"].insert_many(
        [
            {
                "_id": project_id,
                "titulo": "Proyecto visible",
                "usuario_id": USER_ID,
                "created_at": datetime(2026, 1, 1),
            },
            {"_id": ObjectId(), "titulo": "Proyecto ajeno", "usuario_id": "otro-user"},
        ]
    )
    mongo_mock.local_db["Goals"].insert_one(
        {"_id": goal_id, "titulo": "Objetivo", "project_id": project_id, "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {
                "_id": ObjectId(),
                "contenido": "Pendiente",
                "objetivo_id": goal_id,
                "fecha_limite": due_at,
                "estado": "pendiente",
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Completada",
                "objetivo_id": goal_id,
                "estado": "completada",
                "usuario_id": USER_ID,
            },
            {"_id": ObjectId(), "contenido": "Ajena", "usuario_id": "otro-user"},
        ]
    )

    out = tools.get_user_snapshot()
    snapshot = out["snapshot"]

    assert out["success"] is True
    assert snapshot["counts"]["projects"] == 1
    assert snapshot["counts"]["tasks"] == 2
    assert snapshot["counts"]["pending_tasks"] == 1
    assert snapshot["counts"]["completed_tasks"] == 1
    assert snapshot["upcoming_deadlines"][0]["task"]["fecha_limite"] == due_at.isoformat()


def test_get_dashboard_briefing_returns_assistant_tasks_for_initial_dashboard(mongo_mock):
    yesterday = datetime.utcnow() - timedelta(days=1)
    mongo_mock.local_db["Projects"].insert_many(
        [
            {"_id": ObjectId(), "titulo": "Proyecto visible", "usuario_id": USER_ID},
            {"_id": ObjectId(), "titulo": "Proyecto ajeno", "usuario_id": "otro-user"},
        ]
    )
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Tarea vencida",
            "fecha_limite": yesterday,
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    out = tools.get_dashboard_briefing()
    briefing = out["briefing"]

    assert out["success"] is True
    assert briefing["user_id"] == USER_ID
    assert briefing["diagnosis"]["severity"] in {"high", "medium"}
    assert briefing["assistant_tasks"]
    assert any(task["type"] == "suggest_replanning" for task in briefing["assistant_tasks"])
    assert briefing["missing_context"]
    assert "Proyecto ajeno" not in str(briefing)


def test_weekly_planning_session_collects_answers_and_builds_plan(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    task_id = ObjectId()
    due_soon = datetime.utcnow() + timedelta(days=2)
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "TFG", "prioridad": "Alta", "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Goals"].insert_one(
        {"_id": goal_id, "titulo": "Memoria", "project_id": project_id, "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": task_id,
            "contenido": "Escribir introduccion",
            "objetivo_id": goal_id,
            "fecha_limite": due_soon,
            "prioridad": "Alta",
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    start = tools.start_weekly_planning_session()
    session_id = start["planning"]["session"]["_id"]
    repeated = tools.start_weekly_planning_session()

    assert start["success"] is True
    assert start["planning"]["created"] is True
    assert repeated["planning"]["created"] is False
    assert repeated["planning"]["session"]["_id"] == session_id

    answers = [
        ("weekly_available_hours", "4"),
        ("current_energy", "media"),
        ("weekly_top_priorities", "TFG, salud"),
        ("success_criteria", "Tener un borrador defendible"),
    ]
    for field, value in answers:
        out = tools.answer_weekly_planning_question(session_id, field, value)
        assert out["success"] is True

    plan_out = tools.build_weekly_plan(session_id)
    plan = plan_out["planning"]["plan"]

    assert plan_out["success"] is True
    assert plan_out["planning"]["ready"] is True
    assert plan["capacity"]["available_hours"] == 4.0
    assert plan["focus"]["priorities"] == ["TFG", "salud"]
    assert any(item["task"]["_id"] == str(task_id) for item in plan["do_this_week"])
    assert mongo_mock.local_db["PlanningSessions"].count_documents({"usuario_id": USER_ID}) == 1
    stored = mongo_mock.local_db["PlanningSessions"].find_one({"usuario_id": USER_ID})
    assert stored["status"] == "planned"
    assert mongo_mock.local_db["Tasks"].count_documents({"usuario_id": USER_ID}) == 1


def test_weekly_planning_rejects_foreign_session(mongo_mock):
    foreign_id = ObjectId()
    mongo_mock.local_db["PlanningSessions"].insert_one(
        {
            "_id": foreign_id,
            "usuario_id": "otro-user",
            "period_start": datetime.utcnow(),
            "period_end": datetime.utcnow() + timedelta(days=6),
            "status": "active",
            "answers": {},
        }
    )

    out = tools.answer_weekly_planning_question(
        str(foreign_id),
        "weekly_available_hours",
        "5",
    )

    assert out["success"] is False
    assert out["code"] == "planning_validation_error"


def test_should_start_weekly_planning_detects_overdue_work(mongo_mock):
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Vencida",
            "fecha_limite": datetime.utcnow() - timedelta(days=1),
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    out = tools.should_start_weekly_planning()

    assert out["success"] is True
    assert out["planning"]["should_start"] is True
    assert "tareas vencidas" in out["planning"]["reason"]


def test_get_project_context_groups_goals_tasks_documents_and_notes(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    task_id = ObjectId()
    doc_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {
            "_id": project_id,
            "titulo": "TFG",
            "usuario_id": USER_ID,
            "notas": [{"_id": "n1", "text": "nota", "created_at": datetime(2026, 1, 2)}],
        }
    )
    mongo_mock.local_db["Goals"].insert_one(
        {
            "_id": goal_id,
            "titulo": "Redactar",
            "project_id": project_id,
            "progreso": 50,
            "usuario_id": USER_ID,
        }
    )
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {"_id": task_id, "contenido": "Intro", "objetivo_id": goal_id, "usuario_id": USER_ID},
            {"_id": ObjectId(), "contenido": "Ajena", "objetivo_id": goal_id, "usuario_id": "otro"},
        ]
    )
    mongo_mock.local_db["ProjectDocuments"].insert_one(
        {
            "_id": doc_id,
            "original_name": "memoria.pdf",
            "project_id": project_id,
            "usuario_id": USER_ID,
        }
    )

    out = tools.get_project_context(str(project_id))
    context = out["context"]

    assert out["success"] is True
    assert context["project"]["_id"] == str(project_id)
    assert context["goals"][0]["goal"]["_id"] == str(goal_id)
    assert context["goals"][0]["tasks"][0]["_id"] == str(task_id)
    assert context["documents"][0]["_id"] == str(doc_id)
    assert context["notes"][0]["created_at"] == "2026-01-02T00:00:00"
    assert all("Ajena" not in str(goal_group["tasks"]) for goal_group in context["goals"])


def test_get_project_context_rejects_foreign_project(mongo_mock):
    project_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "Ajeno", "usuario_id": "otro-user"}
    )

    out = tools.get_project_context(str(project_id))

    assert out["success"] is False
    assert out["code"] == "project_not_found"


def test_list_and_explain_heuristics():
    listed = tools.list_heuristics(categories=["structure"])
    names = {row["name"] for row in listed["heuristics"]}

    assert listed["success"] is True
    assert "project_without_goals" in names
    assert "overdue_task" not in names

    explained = tools.explain_heuristic("project_without_goals")
    assert explained["success"] is True
    assert explained["heuristic"]["category"] == "structure"


def test_find_atomic_findings_filters_categories_and_uses_homogeneous_shape(mongo_mock):
    project_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "Sin objetivos", "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Vencida",
            "fecha_limite": datetime.utcnow() - timedelta(days=1),
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
    )

    out = tools.find_atomic_findings(categories=["structure"], limit=10)
    finding = out["analysis"]["findings"][0]

    assert out["success"] is True
    assert {item["category"] for item in out["analysis"]["findings"]} == {"structure"}
    assert {
        "type",
        "category",
        "severity",
        "entity",
        "evidence",
        "confidence",
        "explanation",
        "recommendation",
        "suggested_tool",
        "suggested_payload",
        "requires_confirmation",
    }.issubset(finding)


def test_find_bottlenecks_detects_required_patterns(mongo_mock):
    stale_project = ObjectId()
    active_project = ObjectId()
    empty_goal = ObjectId()
    overloaded_goal = ObjectId()
    old = datetime.utcnow() - timedelta(days=90)
    yesterday = datetime.utcnow() - timedelta(days=1)
    mongo_mock.local_db["Projects"].insert_many(
        [
            {
                "_id": stale_project,
                "titulo": "Sin objetivos viejo",
                "usuario_id": USER_ID,
                "created_at": old,
            },
            {
                "_id": active_project,
                "titulo": "Activo",
                "usuario_id": USER_ID,
                "created_at": datetime.utcnow(),
            },
        ]
    )
    mongo_mock.local_db["Goals"].insert_many(
        [
            {
                "_id": empty_goal,
                "titulo": "Sin tareas",
                "project_id": active_project,
                "usuario_id": USER_ID,
            },
            {
                "_id": overloaded_goal,
                "titulo": "Sobrecargado",
                "project_id": active_project,
                "usuario_id": USER_ID,
            },
        ]
    )
    overloaded_tasks = [
        {
            "_id": ObjectId(),
            "contenido": f"Pendiente {idx}",
            "objetivo_id": overloaded_goal,
            "estado": "pendiente",
            "usuario_id": USER_ID,
        }
        for idx in range(3)
    ]
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {
                "_id": ObjectId(),
                "contenido": "Vencida",
                "objetivo_id": overloaded_goal,
                "fecha_limite": yesterday,
                "estado": "pendiente",
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "contenido": "Huerfana",
                "estado": "pendiente",
                "usuario_id": USER_ID,
            },
            {"_id": ObjectId(), "contenido": "Ajena", "estado": "pendiente", "usuario_id": "otro"},
            *overloaded_tasks,
        ]
    )

    out = tools.find_bottlenecks(stale_days=30, overloaded_task_threshold=2)
    types = {item["type"] for item in out["analysis"]["bottlenecks"]}

    assert out["success"] is True
    assert {
        "project_without_goals",
        "goal_without_tasks",
        "overdue_task",
        "orphan_task",
        "stale_project",
        "overloaded_goal",
    }.issubset(types)
    assert "Ajena" not in str(out)


def test_find_emergent_insights_detects_compound_patterns(mongo_mock):
    old = datetime.utcnow() - timedelta(days=90)
    project_ids = [ObjectId(), ObjectId(), ObjectId()]
    goal_ids = [ObjectId(), ObjectId(), ObjectId()]
    mongo_mock.local_db["Projects"].insert_many(
        [
            {
                "_id": project_ids[0],
                "titulo": "Viejo 1",
                "usuario_id": USER_ID,
                "created_at": old,
            },
            {
                "_id": project_ids[1],
                "titulo": "Viejo 2",
                "usuario_id": USER_ID,
                "created_at": old,
            },
            {
                "_id": project_ids[2],
                "titulo": "Doc-heavy",
                "usuario_id": USER_ID,
                "created_at": old,
                "notas": [{"text": "n1"}, {"text": "n2"}],
            },
        ]
    )
    mongo_mock.local_db["Goals"].insert_many(
        [
            {
                "_id": goal_ids[0],
                "titulo": "G1",
                "project_id": project_ids[0],
                "usuario_id": USER_ID,
            },
            {
                "_id": goal_ids[1],
                "titulo": "G2",
                "project_id": project_ids[1],
                "usuario_id": USER_ID,
            },
            {
                "_id": goal_ids[2],
                "titulo": "G3",
                "project_id": project_ids[2],
                "usuario_id": USER_ID,
            },
        ]
    )
    mongo_mock.local_db["ProjectDocuments"].insert_one(
        {
            "_id": ObjectId(),
            "original_name": "paper.pdf",
            "project_id": project_ids[2],
            "uploaded_at": old,
            "usuario_id": USER_ID,
        }
    )

    out = tools.find_emergent_insights(stale_days=30)
    types = {insight["type"] for insight in out["insights"]["insights"]}

    assert out["success"] is True
    assert "operational_drift" in types
    assert "research_without_execution" in types


def test_find_emergent_insights_detects_planning_debt_focus_and_priority_mismatch(mongo_mock):
    old = datetime.utcnow() - timedelta(days=90)
    yesterday = datetime.utcnow() - timedelta(days=1)
    for idx in range(4):
        mongo_mock.local_db["Projects"].insert_one(
            {
                "_id": ObjectId(),
                "titulo": f"Activo {idx}",
                "usuario_id": USER_ID,
                "estado": "Activo",
                "created_at": datetime.utcnow(),
            }
        )
    mongo_mock.local_db["Projects"].insert_one(
        {
            "_id": ObjectId(),
            "titulo": "Alta abandonada",
            "usuario_id": USER_ID,
            "prioridad": "Alta",
            "created_at": old,
        }
    )
    for idx in range(4):
        mongo_mock.local_db["Tasks"].insert_one(
            {
                "_id": ObjectId(),
                "contenido": f"Vencida {idx}",
                "fecha_limite": yesterday,
                "estado": "pendiente",
                "usuario_id": USER_ID,
            }
        )
    for idx in range(4):
        mongo_mock.local_db["Tasks"].insert_one(
            {
                "_id": ObjectId(),
                "contenido": f"Sin fecha {idx}",
                "estado": "pendiente",
                "usuario_id": USER_ID,
            }
        )
    mongo_mock.local_db["Tasks"].insert_one(
        {
            "_id": ObjectId(),
            "contenido": "Alta sin atencion",
            "prioridad": "Alta",
            "estado": "pendiente",
            "fecha_creacion": old,
            "usuario_id": USER_ID,
        }
    )

    out = tools.find_emergent_insights(
        stale_days=30,
        max_active_projects=2,
        max_pending_tasks=3,
    )
    types = {insight["type"] for insight in out["insights"]["insights"]}

    assert {"planning_debt", "focus_fragmentation", "priority_attention_mismatch"}.issubset(types)


def test_analyze_operating_system_and_agent_context_have_expected_shape(mongo_mock):
    project_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {
            "_id": project_id,
            "titulo": "Proyecto",
            "usuario_id": USER_ID,
        }
    )

    analysis = tools.analyze_operating_system()
    context = tools.build_agent_context()

    assert analysis["success"] is True
    assert analysis["analysis"]["snapshot"]["counts"]["projects"] == 1
    assert "atomic_findings" in analysis["analysis"]
    assert "emergent_insights" in analysis["analysis"]
    assert context["success"] is True
    assert context["context"]["identity"]["user_id"] == USER_ID
    assert context["context"]["safety_constraints"]
    assert context["context"]["operating_profile"]["score"]["overall"] <= 100
    assert context["context"]["operating_map"]["summary"]["nodes_total"] >= 1


def test_get_operating_profile_scores_patterns_and_actions_without_executing(mongo_mock):
    old = datetime.utcnow() - timedelta(days=90)
    project_ids = [ObjectId(), ObjectId(), ObjectId()]
    goal_ids = [ObjectId(), ObjectId(), ObjectId()]
    mongo_mock.local_db["Projects"].insert_many(
        [
            {
                "_id": project_ids[0],
                "titulo": "TFG memoria",
                "usuario_id": USER_ID,
                "created_at": old,
            },
            {
                "_id": project_ids[1],
                "titulo": "Ideas agentes",
                "usuario_id": USER_ID,
                "created_at": old,
            },
            {
                "_id": project_ids[2],
                "titulo": "Portfolio",
                "usuario_id": USER_ID,
                "created_at": old,
            },
        ]
    )
    mongo_mock.local_db["Goals"].insert_many(
        [
            {
                "_id": goal_ids[0],
                "titulo": "Escribir marco",
                "project_id": project_ids[0],
                "usuario_id": USER_ID,
            },
            {
                "_id": goal_ids[1],
                "titulo": "Validar heuristicas",
                "project_id": project_ids[1],
                "usuario_id": USER_ID,
            },
            {
                "_id": goal_ids[2],
                "titulo": "Preparar demo",
                "project_id": project_ids[2],
                "usuario_id": USER_ID,
            },
        ]
    )

    out = tools.get_operating_profile(stale_days=30)
    profile = out["profile"]

    assert out["success"] is True
    assert profile["user_id"] == USER_ID
    assert profile["score"]["overall"] < 100
    assert profile["score"]["status"] in {"healthy", "watch", "attention", "critical"}
    assert {"structure", "time", "load", "data_quality", "progress"}.issubset(profile["dimensions"])
    assert any(pattern["type"] == "operational_drift" for pattern in profile["dominant_patterns"])
    assert any(move["tool"] == "create_task" for move in profile["next_best_moves"])
    assert profile["explanation"]
    assert mongo_mock.local_db["Tasks"].count_documents({}) == 0


def test_get_operating_map_links_entities_and_marks_disconnected_items(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    task_id = ObjectId()
    orphan_task_id = ObjectId()
    document_id = ObjectId()
    event_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_many(
        [
            {"_id": project_id, "titulo": "TFG", "usuario_id": USER_ID},
            {"_id": ObjectId(), "titulo": "Ajeno", "usuario_id": "otro-user"},
        ]
    )
    mongo_mock.local_db["Goals"].insert_one(
        {"_id": goal_id, "titulo": "Redactar", "project_id": project_id, "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Tasks"].insert_many(
        [
            {
                "_id": task_id,
                "contenido": "Escribir intro",
                "objetivo_id": goal_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": orphan_task_id,
                "contenido": "Suelta",
                "estado": "pendiente",
                "usuario_id": USER_ID,
            },
        ]
    )
    mongo_mock.local_db["ProjectDocuments"].insert_one(
        {
            "_id": document_id,
            "original_name": "memoria.pdf",
            "project_id": project_id,
            "usuario_id": USER_ID,
        }
    )
    mongo_mock.local_db["Events"].insert_many(
        [
            {
                "_id": event_id,
                "titulo": "Bloque de escritura",
                "id_tarea": task_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "titulo": "Evento suelto",
                "usuario_id": USER_ID,
            },
        ]
    )

    out = tools.get_operating_map(limit=20)
    operating_map = out["operating_map"]
    node_types = {node["type"] for node in operating_map["nodes"]}
    relations = {edge["relation"] for edge in operating_map["edges"]}

    assert out["success"] is True
    assert {"project", "goal", "task", "document", "event"}.issubset(node_types)
    assert {"has_goal", "has_task", "has_document", "scheduled_event"}.issubset(relations)
    assert operating_map["project_summaries"][0]["counts"]["goals"] == 1
    assert operating_map["project_summaries"][0]["counts"]["documents"] == 1
    assert operating_map["disconnected_entities"]["tasks_without_parent"][0]["_id"] == str(
        orphan_task_id
    )
    assert (
        operating_map["disconnected_entities"]["events_without_link"][0]["titulo"]
        == "Evento suelto"
    )
    assert "Ajeno" not in str(operating_map)


def test_suggest_next_actions_returns_payloads_without_executing(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "TFG", "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Goals"].insert_one(
        {
            "_id": goal_id,
            "titulo": "Objetivo sin tareas",
            "project_id": project_id,
            "usuario_id": USER_ID,
        }
    )

    out = tools.suggest_next_actions(limit=5)
    actions = out["suggestions"]["actions"]

    assert out["success"] is True
    assert any(action["suggested_tool"] == "create_task" for action in actions)
    create_task_action = next(
        action for action in actions if action["suggested_tool"] == "create_task"
    )
    assert create_task_action["suggested_payload"]["goal_id"] == str(goal_id)
    assert create_task_action["requires_confirmation"] is False
    assert mongo_mock.local_db["Tasks"].count_documents({}) == 0


def test_health_check_reports_storage_without_secrets(mongo_mock):
    out = tools.health_check()

    assert out["success"] is True
    assert out["user_id"] == USER_ID
    assert out["checks"]["local_database"] is True
    assert out["checks"]["remote_database"] is True
    assert "MONGO" not in str(out)


def test_create_and_update_project_goal_task_flow(mongo_mock, capsys):
    project_out = tools.create_project(
        titulo="TFG",
        descripcion="Trabajo final",
        prioridad="Alta",
    )
    project_id = project_out["project"]["_id"]
    project_update = tools.update_project(
        project_id=project_id,
        descripcion="Trabajo final actualizado",
        progreso=40,
    )
    goal_out = tools.create_goal(
        titulo="Redactar memoria",
        project_id=project_id,
        prioridad="Alta",
    )
    goal_id = goal_out["goal"]["_id"]
    goal_update = tools.update_goal(
        goal_id=goal_id,
        progreso=25,
        descripcion="Primer bloque",
    )
    task_out = tools.create_task(
        contenido="Escribir introduccion",
        goal_id=goal_id,
        prioridad="alta",
    )
    task_id = task_out["task"]["_id"]
    task_update = tools.update_task(
        task_id=task_id,
        estado="completada",
        descripcion="Cerrada desde MCP",
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert project_out["success"] is True
    assert project_update["project"]["descripcion"] == "Trabajo final actualizado"
    assert project_update["project"]["progreso"] == 40
    assert goal_out["goal"]["project_id"] == project_id
    assert goal_update["goal"]["progreso"] == 25
    assert task_out["task"]["project_id"] == project_id
    assert task_update["task"]["estado"] == "completada"
    assert mongo_mock.local_db["Projects"].count_documents({}) == 1
    assert mongo_mock.local_db["Goals"].count_documents({}) == 1
    assert mongo_mock.local_db["Tasks"].count_documents({}) == 1


def test_motor_tools_reject_foreign_entities(mongo_mock):
    project_id = ObjectId()
    goal_id = ObjectId()
    task_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "Ajeno", "usuario_id": "otro-user"}
    )
    mongo_mock.local_db["Goals"].insert_one(
        {"_id": goal_id, "titulo": "Ajeno", "project_id": project_id, "usuario_id": "otro-user"}
    )
    mongo_mock.local_db["Tasks"].insert_one(
        {"_id": task_id, "contenido": "Ajena", "objetivo_id": goal_id, "usuario_id": "otro-user"}
    )

    assert tools.update_project(str(project_id), titulo="No")["code"] == "project_not_found"
    assert tools.create_goal("No", project_id=str(project_id))["code"] == "project_not_found"
    assert tools.update_goal(str(goal_id), titulo="No")["code"] == "goal_not_found"
    assert tools.update_task(str(task_id), contenido="No")["code"] == "task_not_found"
    assert tools.add_project_note(str(project_id), "No")["code"] == "project_not_found"
    assert mongo_mock.local_db["Projects"].find_one({"_id": project_id})["titulo"] == "Ajeno"


def test_project_notes_and_documents_are_user_scoped(mongo_mock):
    project_id = ObjectId()
    doc_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_many(
        [
            {"_id": project_id, "titulo": "TFG", "usuario_id": USER_ID},
            {"_id": ObjectId(), "titulo": "Ajeno", "usuario_id": "otro-user"},
        ]
    )
    mongo_mock.local_db["ProjectDocuments"].insert_many(
        [
            {
                "_id": doc_id,
                "original_name": "memoria.pdf",
                "project_id": project_id,
                "usuario_id": USER_ID,
            },
            {
                "_id": ObjectId(),
                "original_name": "ajeno.pdf",
                "project_id": project_id,
                "usuario_id": "otro-user",
            },
        ]
    )

    note_out = tools.add_project_note(str(project_id), "Idea de estructura")
    docs_out = tools.list_project_documents(str(project_id))

    assert note_out["success"] is True
    assert note_out["note"]["text"] == "Idea de estructura"
    assert len(note_out["project"]["notas"]) == 1
    assert docs_out["success"] is True
    assert docs_out["count"] == 1
    assert docs_out["documents"][0]["_id"] == str(doc_id)
    assert "ajeno.pdf" not in str(docs_out)


def test_sync_now_pushes_local_documents_when_remote_available(mongo_mock):
    project_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "Para remoto", "usuario_id": USER_ID}
    )

    out = tools.sync_now()

    assert out["success"] is True
    assert out["sync"]["pushed_documents"] >= 1
    assert mongo_mock.remote_db["Projects"].find_one({"_id": project_id})["titulo"] == "Para remoto"


def test_create_task_links_to_goal_and_project_without_stdout_noise(mongo_mock, capsys):
    project_id = ObjectId()
    goal_id = ObjectId()
    mongo_mock.local_db["Projects"].insert_one(
        {"_id": project_id, "titulo": "TFG", "usuario_id": USER_ID}
    )
    mongo_mock.local_db["Goals"].insert_one(
        {
            "_id": goal_id,
            "titulo": "Redactar memoria",
            "project_id": project_id,
            "usuario_id": USER_ID,
        }
    )

    out = tools.create_task(
        contenido="Escribir introduccion",
        goal_id=str(goal_id),
        prioridad="alta",
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert out["success"] is True
    assert out["task"]["contenido"] == "Escribir introduccion"
    assert out["task"]["objetivo_id"] == str(goal_id)
    assert out["task"]["project_id"] == str(project_id)
    assert mongo_mock.local_db["Tasks"].count_documents({"usuario_id": USER_ID}) == 1


def test_create_task_rejects_blank_content(mongo_mock):
    out = tools.create_task(contenido="  ")

    assert out["success"] is False
    assert out["code"] == "invalid_request"
    assert out["field"] == "contenido"


def test_create_task_rejects_foreign_goal(mongo_mock):
    goal_id = ObjectId()
    mongo_mock.local_db["Goals"].insert_one(
        {"_id": goal_id, "titulo": "Ajeno", "usuario_id": "otro-user"}
    )

    out = tools.create_task(contenido="No deberia entrar", goal_id=str(goal_id))

    assert out["success"] is False
    assert out["code"] == "goal_not_found"
    assert mongo_mock.local_db["Tasks"].count_documents({}) == 0


def test_create_task_rejects_invalid_project_id(mongo_mock):
    out = tools.create_task(contenido="x", project_id="no-es-objectid")

    assert out["success"] is False
    assert out["code"] == "invalid_object_id"
