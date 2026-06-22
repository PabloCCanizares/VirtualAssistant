import json
from datetime import datetime

from bson import ObjectId

from model.category_model import CategoryModel
from model.event_model import eventModel
from model.goal_model import GoalModel
from model.project_document_model import ProjectDocumentModel
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
    events = eventModel.get_events_by_user(user_id)

    return {
        "user_id": str(user_id),
        "tasks": [_serialize_value(task) for task in tasks],
        "goals": [_serialize_value(goal) for goal in goals],
        "projects": [_serialize_value(project) for project in projects],
        "events": [_serialize_value(e) for e in events],
    }


def get_user_context_json(user_id) -> str:
    return json.dumps(_load_user_context(user_id), ensure_ascii=True)


_COLLECTION_LOADERS = {
    "projects":   lambda uid: [_serialize_value(p) for p in ProjectModel.get_by_user_id(uid)],
    "goals":      lambda uid: [_serialize_value(g) for g in GoalModel.get_by_user_id(uid)],
    "tasks":      lambda uid: [_serialize_value(t) for t in TaskModel.get_task_by_user(uid)],
    "events":     lambda uid: [_serialize_value(e) for e in eventModel.get_events_by_user(uid)],
    "documents":  lambda uid: [_serialize_value(d) for d in ProjectDocumentModel.get_all_documents(usuario_id=uid)],
    "categories": lambda uid: [_serialize_value(c) for c in CategoryModel.get_all_categories(usuario_id=uid)],
}


def load_user_collections(user_id, collections: list) -> str:
    """Carga selectivamente solo las colecciones solicitadas para el usuario."""
    data = {"user_id": str(user_id)}
    for col in collections:
        loader = _COLLECTION_LOADERS.get(col)
        if loader:
            data[col] = loader(user_id)
    return json.dumps(data, ensure_ascii=True)
