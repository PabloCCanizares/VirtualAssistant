import json
from datetime import datetime
from bson import ObjectId
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from model.goal_model import GoalModel
from model.project_model import ProjectModel
from model.task_model import TaskModel
from database.mongo_conn import get_app_user_id

DEFAULT_USER_ID = get_app_user_id()

"""Convertir los objetos no seriablizables a formatos compatibles con JSON para meterlos en MongoDB.""
"""
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


"""Cargar contexto del usuario: tareas, objetivos y proyectos del usuario desde la base de datos y serializarlos a JSON."""
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


"""Construir el prompt, proporcionar el contexto del usuario y el historial de chat."""
def _build_messages(user_message, history, context_json):
    system_prompt = (
        "Eres GoalMind AI, un asistente para ayudar con objetivos, tareas y "
        "planificacion. Responde en espanol de forma clara y concisa."
    )
    messages = [
        SystemMessage(content=system_prompt),
        SystemMessage(content=f"Contexto del usuario (JSON): {context_json}"),
    ]

    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))
    return messages


"""Ejecutar el chat con el modelo LLM de OpenAI."""
def run_chat(message, history):
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY no configurada")

    user_id = settings.default_user_id or DEFAULT_USER_ID
    context_json = json.dumps(_load_user_context(user_id), ensure_ascii=True)

    llm = ChatOpenAI(model=settings.openai_model, temperature=0.3)
    messages = _build_messages(message, history, context_json)
    response = llm.invoke(messages)
    return response.content
