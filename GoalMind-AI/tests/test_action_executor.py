import ai.agents.action_executor as executor_module
from ai.agents.action_executor import action_executor_node


def test_delete_goal_requires_confirmation():
    state = {
        "action_name": "delete_goal",
        "action_parameters": {"goal_id": "g1"},
        "action_confirmed": False,
        "context_json": "{}",
        "user_id": "u1",
    }
    result = action_executor_node(state, None)
    assert "requiere confirmacion" in result["final_response"].lower()


def test_create_project_requires_title():
    state = {
        "action_name": "create_project",
        "action_parameters": {},
        "context_json": "{}",
        "user_id": "u1",
    }
    result = action_executor_node(state, None)
    assert "titulo del proyecto" in result["final_response"].lower()


def test_delete_project_cascade_invokes_models(monkeypatch):
    calls = []

    monkeypatch.setattr(
        executor_module.GoalModel,
        "get_by_project",
        lambda project_id, usuario_id=None: [{"_id": "g1"}],
    )
    monkeypatch.setattr(
        executor_module.TaskModel,
        "get_tasks_by_goal",
        lambda goal_id, usuario_id=None: [{"_id": "t1"}],
    )
    monkeypatch.setattr(
        executor_module.TaskModel,
        "delete_tasks_by_ids",
        lambda ids, usuario_id=None: calls.append(("delete_tasks", list(ids))),
    )
    monkeypatch.setattr(
        executor_module.GoalModel,
        "delete_goals_by_ids",
        lambda ids, usuario_id=None: calls.append(("delete_goals", list(ids))),
    )
    monkeypatch.setattr(
        executor_module.ProjectDocumentModel,
        "get_by_project",
        lambda project_id, usuario_id=None: [{"_id": "d1", "local_path": None}],
    )
    monkeypatch.setattr(
        executor_module.ProjectDocumentModel,
        "delete_document",
        lambda doc_id, usuario_id=None: calls.append(("delete_doc", doc_id)),
    )
    monkeypatch.setattr(
        executor_module.ProjectModel,
        "delete_project",
        lambda project_id: calls.append(("delete_project", project_id)),
    )
    monkeypatch.setattr(
        executor_module,
        "queue_deletion",
        lambda collection, item_id: calls.append(("queue", collection, str(item_id))),
    )
    monkeypatch.setattr(
        executor_module,
        "flush_deletion_queue",
        lambda: calls.append(("flush_queue",)),
    )
    monkeypatch.setattr(
        executor_module,
        "clear_pending_action",
        lambda user_id: calls.append(("clear_pending", user_id)),
    )

    state = {
        "action_name": "delete_project",
        "action_parameters": {"project_id": "p1"},
        "action_confirmed": True,
        "context_json": "{}",
        "user_id": "u1",
    }
    result = action_executor_node(state, None)

    assert "proyecto eliminado" in result["final_response"].lower()

    step_names = [item[0] for item in calls]
    assert "delete_tasks" in step_names
    assert "delete_goals" in step_names
    assert "delete_project" in step_names
    assert step_names.index("delete_tasks") < step_names.index("delete_goals")
    assert step_names.index("delete_goals") < step_names.index("delete_project")
