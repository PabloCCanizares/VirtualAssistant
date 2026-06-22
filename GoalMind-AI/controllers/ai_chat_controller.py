import json
import logging

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ai.chat import stream_chat
from ai.config import get_chat_model_catalog

logger = logging.getLogger(__name__)

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
    model_id = payload.get("model_id")

    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    def generate():
        try:
            for event_type, data in stream_chat(
                user_message,
                history,
                deep_search_mode,
                model_id=model_id,
            ):
                payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            error_payload = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_payload}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@ai_chat_bp.get("/api/ai/models")
def ai_chat_models():
    return jsonify(get_chat_model_catalog())


@ai_chat_bp.post("/api/ai/summarize-document")
def summarize_document():
    from ai.services.doc_summarize_service import summarize_and_save_note

    payload = request.get_json(silent=True) or {}
    doc_id = (payload.get("doc_id") or "").strip()
    project_id = (payload.get("project_id") or "").strip()

    if not doc_id or not project_id:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    try:
        message = summarize_and_save_note(doc_id, project_id)
        return jsonify({"success": True, "message": message})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except Exception:
        logger.exception("summarize_document: error inesperado")
        return jsonify({"success": False, "message": "Error al generar el resumen"}), 500
