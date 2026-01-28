from flask import Blueprint, jsonify, request
from chat import run_chat

ai_chat_bp = Blueprint("ai_chat_bp", __name__)


@ai_chat_bp.post("/api/ai/chat")
def ai_chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    history = payload.get("history") or []

    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    try:
        reply = run_chat(user_message, history)
        return jsonify({"reply": reply})
    except Exception as exc:
        return jsonify({"error": f"Error al generar respuesta: {exc}"}), 500
