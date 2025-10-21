from flask import Blueprint, jsonify, request
from database.mongo_conn import mongo
from bson.objectid import ObjectId

goal_bp = Blueprint("goals", __name__)


def _serialize_goal(goal):
    """Normaliza el documento de Mongo para exponerlo al frontend."""
    goal["_id"] = str(goal["_id"])
    return goal


@goal_bp.route("/goals", methods=["POST"])
def create_goal():
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    scope = data.get("scope")

    required_fields = ["title", "scope"]
    missing = [field for field in required_fields if not (title if field == "title" else data.get(field))]
    if missing:
        return (
            jsonify({"error": f"missing fields: {', '.join(missing)}"}),
            400,
        )

    allowed_scopes = {"short", "medium", "long"}
    if scope not in allowed_scopes:
        return jsonify({"error": "invalid scope"}), 400

    progress_value = 0
    if data.get("progress") not in (None, ""):
        try:
            progress_value = float(data["progress"])
        except (TypeError, ValueError):
            return jsonify({"error": "progress must be a number"}), 400
        if progress_value < 0 or progress_value > 100:
            return jsonify({"error": "progress must be between 0 and 100"}), 400

    # Normalización ligera de datos
    payload = {
        "title": title,
        "scope": scope,
        "description": (data.get("description") or "").strip(),
        "category": (data.get("category") or "").strip(),
        "progress": progress_value,
        "deadline": (data.get("deadline") or "").strip() or None,
    }

    result = mongo.db.Goals.insert_one(payload)
    return jsonify({"inserted_id": str(result.inserted_id)}), 201


def get_all_goals_from_db():
    goals = list(mongo.db.Goals.find())
    return [_serialize_goal(goal) for goal in goals]


@goal_bp.route("/goals", methods=["GET"])
def get_all_goals():
    return jsonify(get_all_goals_from_db()), 200


@goal_bp.route("/goals/<goal_id>", methods=["GET"])
def get_goal(goal_id):
    try:
        oid = ObjectId(goal_id)
    except Exception:
        return jsonify({"error": "invalid id"}), 400

    doc = mongo.db.Goals.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "not found"}), 404

    return jsonify(_serialize_goal(doc)), 200
