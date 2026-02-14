import json
from datetime import datetime

from bson import ObjectId

from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel


def _serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def _load_user_context(user_id):
    tasks = TaskModel.get_task_by_user(user_id)
    goals = GoalModel.get_by_user_id(user_id)
    projects = ProjectModel.get_by_user_id(user_id)

    return {
        "user_id": str(user_id),
        "tasks": [_serialize_value(task) for task in tasks],
        "goals": [_serialize_value(goal) for goal in goals],
        "projects": [_serialize_value(project) for project in projects],
    }


def get_user_context_json(user_id) -> str:
    return json.dumps(_load_user_context(user_id), ensure_ascii=True)
