from flask import Blueprint, jsonify, request
from database.mongo_conn import get_collection, internet_available, mongo, sync_to_remote
from bson.objectid import ObjectId   #Para convertir el id

task_bp = Blueprint('tasks', __name__)

@task_bp.route("/tasks", methods=["GET"])
def get_tasks():
    local_col, _ = get_collection("Tasks")

    # Si hay conexión, sincroniza todos los documentos locales
    if internet_available():
        tareas_locales = list(local_col.find({}))
        for t in tareas_locales:
            sync_to_remote("Tasks", t)

    # Siempre devolvemos lo local
    tasks = list(local_col.find({}, {"_id": 0}))
    return jsonify(tasks), 200

def get_all_tasks_from_db():
    tasks = list(mongo.db.Tasks.find())
    for task in tasks:
        task['_id'] = str(task['_id'])
    return tasks

@task_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    try:
        oid = ObjectId(task_id)
    except Exception:
        return jsonify({"error": "invalid id"}), 400

    doc = mongo.db.Tasks.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "not found"}), 404

    doc["_id"] = str(doc["_id"])
    return jsonify(doc), 200

@task_bp.route('/tasks/<task_id>', methods=['PATCH'])
def update_task(task_id):
    try:
        oid = ObjectId(task_id)
    except Exception:
        return jsonify({"error": "invalid id"}), 400

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "empty body"}), 400

    res = mongo.db.Tasks.update_one({"_id": oid}, {"$set": data})
    if res.matched_count == 0:
        return jsonify({"error": "not found"}), 404

    # devolver el documento actualizado
    updated = mongo.db.Tasks.find_one({"_id": oid})
    updated["_id"] = str(updated["_id"])
    return jsonify(updated), 200

@task_bp.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        oid = ObjectId(task_id)
    except Exception:
        return jsonify({"error": "invalid id"}), 400

    res = mongo.db.Tasks.delete_one({"_id": oid})
    if res.deleted_count == 0:
        return jsonify({"error": "not found"}), 404

    return jsonify({"deleted_id": task_id}), 200
