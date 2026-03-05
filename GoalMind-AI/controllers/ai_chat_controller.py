from flask import Blueprint, jsonify, request
from ai.config import get_chat_model_catalog
from ai.chat import run_chat

ai_chat_bp = Blueprint("ai_chat_bp", __name__)


@ai_chat_bp.post("/api/ai/chat")
def ai_chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    model_id = payload.get("model_id")

    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    try:
        reply = run_chat(user_message, history, model_id=model_id)
        return jsonify({"reply": reply})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error al generar respuesta: {exc}"}), 500


@ai_chat_bp.get("/api/ai/models")
def ai_chat_models():
    try:
        return jsonify(get_chat_model_catalog())
    except Exception as exc:
        return jsonify({"error": f"No se pudo cargar el catalogo de modelos: {exc}"}), 500
