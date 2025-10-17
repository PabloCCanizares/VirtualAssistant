from flask import Blueprint, jsonify, request
from database.mongo_conn import mongo

task_bp = Blueprint('tasks', __name__)

@task_bp.route('/tasks', methods=['POST'])
def create_task():
    data = request.get_json()
    result = mongo.db.Tasks.insert_one(data)
    return jsonify({"inserted_id": str(result.inserted_id)}), 201

def get_all_tasks_from_db():
    tasks = list(mongo.db.Tasks.find())
    for task in tasks:
        task['_id'] = str(task['_id'])
    return tasks

@task_bp.route('/tasks', methods=['GET'])
def get_all_tasks():
    tasks = get_all_tasks_from_db()
    return jsonify(tasks), 200