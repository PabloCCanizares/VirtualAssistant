import json

from flask import Blueprint, Response, jsonify, request
from ai.config import get_chat_model_catalog
from ai.chat import stream_chat

ai_chat_bp = Blueprint("ai_chat_bp", __name__)


def _normalize_deep_search_mode(value):
    mode = (value or "").strip().lower()
    if not mode:
        return None
    return mode if mode in {"auto", "on", "off"} else "auto"


@ai_chat_bp.post("/api/ai/chat")
def ai_chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    history = payload.get("history") or []
    model_id = payload.get("model_id")
    deep_search_mode = _normalize_deep_search_mode(payload.get("deep_search_mode"))

    if not user_message:
        return jsonify({"error": "Mensaje vacio"}), 400

    def _events():
        try:
            for event_type, data in stream_chat(
                user_message,
                history,
                model_id=model_id,
                deep_search_mode=deep_search_mode,
            ):
                payload = {"type": event_type}
                if isinstance(data, dict):
                    payload.update(data)
                elif event_type == "done":
                    payload["reply"] = str(data)
                else:
                    payload["message"] = str(data)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            message = f"Error al generar respuesta: {exc}"
            yield f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"

    return Response(_events(), mimetype="text/event-stream")


@ai_chat_bp.get("/api/ai/models")
def ai_chat_models():
    try:
        return jsonify(get_chat_model_catalog())
    except Exception as exc:
        return jsonify({"error": f"No se pudo cargar el catalogo de modelos: {exc}"}), 500


@ai_chat_bp.post("/api/ai/summarize-document")
def summarize_document():
    payload = request.get_json(silent=True) or {}
    doc_id = (payload.get("doc_id") or "").strip()
    project_id = (payload.get("project_id") or "").strip()

    if not doc_id or not project_id:
        return jsonify({"success": False, "message": "doc_id y project_id son obligatorios"}), 400

    try:
        from ai.services.doc_summarize_service import summarize_and_save_note

        message = summarize_and_save_note(doc_id, project_id)
        return jsonify({"success": True, "message": message})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "message": f"Error al resumir documento: {exc}"}), 500
