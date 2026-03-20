import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ai.chat import stream_chat

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

    def generate():
        try:
            for event_type, data in stream_chat(user_message, history, deep_search_mode):
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
