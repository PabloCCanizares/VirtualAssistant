from flask import Blueprint, jsonify, request
from bson.objectid import ObjectId
from database.mongo_conn import mongo

event_bp = Blueprint("events", __name__)

DAY_KEYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
COLOR_KEYS = {"blue", "violet", "green"}


def _normalize_time(value):
    if not value:
        return None
    value = value.strip()
    if len(value) != 5 or value[2] != ":":
        return None
    hh, mm = value.split(":")
    if not (hh.isdigit() and mm.isdigit()):
        return None
    hour = int(hh)
    minute = int(mm)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _serialize_event(event):
    event["_id"] = str(event["_id"])
    return event


@event_bp.route("/events", methods=["POST"])
def create_event():
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    day = data.get("day")
    start = _normalize_time(data.get("start"))
    end = _normalize_time(data.get("end"))
    color = (data.get("color") or "blue").lower()

    missing = []
    if not title:
        missing.append("title")
    if day not in DAY_KEYS:
        missing.append("day")
    if start is None:
        missing.append("start")
    if missing:
        return jsonify({"error": f"missing or invalid fields: {', '.join(missing)}"}), 400

    if end is not None and end <= start:
        return jsonify({"error": "end must be after start"}), 400

    if color not in COLOR_KEYS:
        color = "blue"

    payload = {
        "title": title,
        "day": day,
        "start": start,
        "end": end,
        "color": color,
        "description": (data.get("description") or "").strip(),
    }

    result = mongo.db.Events.insert_one(payload)
    return jsonify({"inserted_id": str(result.inserted_id)}), 201


@event_bp.route("/events", methods=["GET"])
def get_events():
    events = list(mongo.db.Events.find())
    return jsonify([_serialize_event(ev) for ev in events]), 200


@event_bp.route("/events/<event_id>", methods=["DELETE"])
def delete_event(event_id):
    try:
        oid = ObjectId(event_id)
    except Exception:
        return jsonify({"error": "invalid id"}), 400

    res = mongo.db.Events.delete_one({"_id": oid})
    if res.deleted_count == 0:
        return jsonify({"error": "not found"}), 404

    return jsonify({"deleted_id": event_id}), 200
