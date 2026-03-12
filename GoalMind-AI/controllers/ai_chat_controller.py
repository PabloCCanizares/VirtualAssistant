from flask import Blueprint, jsonify, request
from ai.chat import run_chat

ai_chat_bp = Blueprint("ai_chat_bp", __name__)
ALLOWED_DEEP_SEARCH_MODES = {"auto", "on", "off"}


def _normalize_deep_search_mode(value):
    mode = (value or "").strip().lower()
    if not mode:
        return None
    if mode in ALLOWED_DEEP_SEARCH_MODES:
        return mode
    return "auto"


@ai_chat_bp.post("/api/ai/chat")
def ai_chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    deep_search_mode = _normalize_deep_search_mode(payload.get("deep_search_mode"))

    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    try:
        reply = run_chat(user_message, history, deep_search_mode=deep_search_mode)
        return jsonify({"reply": reply})
    except Exception as exc:
        return jsonify({"error": f"Error al generar respuesta: {exc}"}), 500
