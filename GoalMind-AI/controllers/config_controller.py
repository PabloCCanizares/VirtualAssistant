import os
import logging
from pathlib import Path

from flask import Blueprint, jsonify, request
from dotenv import set_key
from pymongo import MongoClient
import certifi
try:
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None
try:
    from groq import Groq
except ModuleNotFoundError:
    Groq = None
try:
    import google.generativeai as genai
except ModuleNotFoundError:
    genai = None

from database.mongo_conn import (
    reconnect_databases,
    ENV_PATH,
    ensure_remote_connection,
    flush_deletion_queue,
    sync_all_collections,
    sync_local_to_remote,
)

logger = logging.getLogger(__name__)

config_bp = Blueprint("config_bp", __name__, url_prefix="/config")

# ---------------------------------------------------------------------------
# Schema: secciones, campos, tipos, defaults y validacion
# ---------------------------------------------------------------------------
SETTINGS_SCHEMA = {
    "app": {
        "label": "Aplicacion",
        "fields": {
            "FLASK_DEBUG": {
                "label": "Modo debug",
                "type": "select",
                "choices": ["0", "1"],
                "default": "1",
                "restart_required": True,
            },
            "LOG_LEVEL": {
                "label": "Nivel de log",
                "type": "select",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR"],
                "default": "INFO",
            },
            "TZ": {"label": "Zona horaria", "type": "text", "default": "Europe/Madrid"},
        },
    },
    "ai": {
        "label": "IA / LLM",
        "fields": {
            "LLM_PROVIDER": {
                "label": "Proveedor LLM",
                "type": "select",
                "choices": ["openai", "gemini", "groq"],
                "default": "openai",
            },
            "OPENAI_API_KEY": {"label": "OpenAI API Key", "type": "text", "default": ""},
            "OPENAI_MODEL": {"label": "Modelo OpenAI", "type": "text", "default": "gpt-5-nano"},
            "GEMINI_API_KEY": {"label": "Gemini API Key", "type": "text", "default": ""},
            "GEMINI_MODEL": {
                "label": "Modelo Gemini",
                "type": "text",
                "default": "gemini-2.5-flash",
            },
            "GROQ_API_KEY": {"label": "Groq API Key", "type": "text", "default": ""},
            "GROQ_MODEL": {
                "label": "Modelo Groq",
                "type": "text",
                "default": "llama-3.1-8b-instant",
            },
        },
    },
    "deep_search": {
        "label": "Busqueda Profunda",
        "fields": {
            "DEEP_SEARCH_ENABLED": {
                "label": "Habilitada",
                "type": "select",
                "choices": ["0", "1"],
                "default": "0",
            },
            "DEEP_SEARCH_PROVIDER": {
                "label": "Proveedor",
                "type": "select",
                "choices": ["tavily", "serper", "brave"],
                "default": "tavily",
            },
            "DEEP_SEARCH_API_KEY": {"label": "API Key", "type": "text", "default": ""},
            "DEEP_SEARCH_MAX_RESULTS": {
                "label": "Max resultados",
                "type": "number",
                "default": "8",
                "min": 1,
                "max": 20,
            },
            "DEEP_SEARCH_TIMEOUT_SECONDS": {
                "label": "Timeout (seg)",
                "type": "number",
                "default": "10",
                "min": 3,
                "max": 60,
            },
            "DEEP_SEARCH_MAX_SOURCES": {
                "label": "Max fuentes",
                "type": "number",
                "default": "5",
                "min": 1,
                "max": 12,
            },
            "DEEP_SEARCH_MODE_DEFAULT": {
                "label": "Modo por defecto",
                "type": "select",
                "choices": ["auto", "on", "off"],
                "default": "auto",
            },
        },
    },
    "mongodb": {
        "label": "MongoDB",
        "fields": {
            "MONGO_LOCAL_URI": {
                "label": "URI Local",
                "type": "text",
                "default": "mongodb://127.0.0.1:27017",
            },
            "MONGO_LOCAL_DB": {
                "label": "Base de datos Local",
                "type": "text",
                "default": "VirtualAssistantDB",
            },
            "MONGO_REMOTE_URI": {
                "label": "URI Remota (Atlas)",
                "type": "text",
                "default": "",
            },
            "MONGO_REMOTE_DB": {
                "label": "Base de datos Remota",
                "type": "text",
                "default": "VirtualAssistantDB",
            },
        },
    },
}

# Mapa plano key → field_meta para acceso rapido
_FLAT_FIELDS = {}
for _sec in SETTINGS_SCHEMA.values():
    for _key, _meta in _sec["fields"].items():
        _FLAT_FIELDS[_key] = _meta

MONGO_KEYS = {"MONGO_LOCAL_URI", "MONGO_LOCAL_DB", "MONGO_REMOTE_URI", "MONGO_REMOTE_DB"}
API_KEY_FIELDS = {"OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"}


# ---------------------------------------------------------------------------
# GET /config/api/settings
# ---------------------------------------------------------------------------
@config_bp.route("/api/settings", methods=["GET"])
def get_settings():
    sections = {}
    for section_key, section in SETTINGS_SCHEMA.items():
        fields = {}
        for key, meta in section["fields"].items():
            fields[key] = os.getenv(key, meta["default"])
        sections[section_key] = fields
    return jsonify({"success": True, "sections": sections, "schema": SETTINGS_SCHEMA})


# ---------------------------------------------------------------------------
# POST /config/api/apply
# ---------------------------------------------------------------------------
@config_bp.route("/api/apply", methods=["POST"])
def apply_settings():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"success": False, "errors": {"_global": "No se recibieron datos"}}), 400

    # Validar keys conocidas
    errors = {}
    for key in data:
        if key not in _FLAT_FIELDS:
            errors[key] = "Campo desconocido"
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    # Validar tipos
    for key, value in data.items():
        meta = _FLAT_FIELDS[key]
        if meta["type"] == "select" and value not in meta.get("choices", []):
            errors[key] = f"Valor no permitido. Opciones: {', '.join(meta['choices'])}"
        if meta["type"] == "number":
            try:
                num = int(value)
                if "min" in meta and num < meta["min"]:
                    errors[key] = f"Minimo permitido: {meta['min']}"
                if "max" in meta and num > meta["max"]:
                    errors[key] = f"Maximo permitido: {meta['max']}"
            except (ValueError, TypeError):
                errors[key] = "Debe ser un numero entero"
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    # Guardar snapshot para rollback
    old_values = {key: os.getenv(key, "") for key in data}

    # Persistir en .env y os.environ
    for key, value in data.items():
        set_key(str(ENV_PATH), key, value, quote_mode="never")
        os.environ[key] = value

    # Validar API keys cambiadas
    changed_api_keys = API_KEY_FIELDS & set(data.keys())
    if changed_api_keys:
        api_errors = _validate_api_keys(data, changed_api_keys)
        if api_errors:
            errors.update(api_errors)

    # Reconectar MongoDB si cambiaron URIs
    changed_mongo = MONGO_KEYS & set(data.keys())
    if changed_mongo:
        result = reconnect_databases()
        for err in result.get("errors", []):
            field = err.split(":")[0].strip() if ":" in err else "MONGO_LOCAL_URI"
            errors[field] = err

    # Si hubo errores, revertir los campos fallidos
    if errors:
        for key in errors:
            if key in old_values:
                set_key(str(ENV_PATH), key, old_values[key], quote_mode="never")
                os.environ[key] = old_values[key]
        # Re-reconectar si revertimos MongoDB
        if MONGO_KEYS & set(errors.keys()):
            reconnect_databases()
        return jsonify({"success": False, "errors": errors}), 400

    # Comprobar si algun campo requiere reinicio
    restart_required = any(
        _FLAT_FIELDS.get(k, {}).get("restart_required", False) for k in data
    )

    return jsonify({
        "success": True,
        "message": "Cambios aplicados correctamente",
        "restart_required": restart_required,
    })


# ---------------------------------------------------------------------------
# POST /config/api/test-mongo-local
# ---------------------------------------------------------------------------
@config_bp.route("/api/test-mongo-local", methods=["POST"])
def test_mongo_local():
    data = request.get_json(silent=True) or {}
    uri = (data.get("uri") or "").strip()
    if not uri:
        return jsonify({"success": False, "message": "URI vacia"}), 400
    if not uri.startswith("mongodb://"):
        return jsonify({"success": False, "message": "URI local debe comenzar con mongodb://"}), 400
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()
        return jsonify({"success": True, "message": "Conexion exitosa"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


# ---------------------------------------------------------------------------
# POST /config/api/test-mongo-remote
# ---------------------------------------------------------------------------
@config_bp.route("/api/test-mongo-remote", methods=["POST"])
def test_mongo_remote():
    data = request.get_json(silent=True) or {}
    uri = (data.get("uri") or "").strip()
    if not uri:
        return jsonify({"success": False, "message": "URI vacia"}), 400
    if not uri.startswith("mongodb+srv://"):
        return jsonify({"success": False, "message": "URI remota debe comenzar con mongodb+srv://"}), 400
    try:
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()
        return jsonify({"success": True, "message": "Conexion exitosa"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


# ---------------------------------------------------------------------------
# POST /config/api/sync-now
# ---------------------------------------------------------------------------
@config_bp.route("/api/sync-now", methods=["POST"])
def sync_now():
    """Ejecuta sincronización completa manual entre BD local y remota."""
    from flask import current_app
    from model.project_document_model import ProjectDocumentModel

    try:
        if not ensure_remote_connection(current_app):
            return jsonify({"success": False, "error": "No hay conexión con la base de datos remota"}), 503
        flush_deletion_queue()
        ProjectDocumentModel.promote_pending_remote_uploads(app=current_app)
        sync_all_collections()
        sync_local_to_remote()
        return jsonify({"success": True})
    except Exception as exc:
        logger.error("[Config] Error en sincronización manual: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Validacion de API keys
# ---------------------------------------------------------------------------
def _validate_api_keys(data, changed_keys):
    errors = {}

    if "OPENAI_API_KEY" in changed_keys:
        key = data["OPENAI_API_KEY"]
        if key:
            if OpenAI is None:
                errors["OPENAI_API_KEY"] = (
                    "Falta dependencia opcional 'openai'. "
                    "Instala requirements para validar claves de OpenAI."
                )
            else:
                try:
                    client = OpenAI(api_key=key)
                    client.models.list()
                except Exception as exc:
                    errors["OPENAI_API_KEY"] = f"Clave invalida: {exc}"

    if "GEMINI_API_KEY" in changed_keys:
        key = data["GEMINI_API_KEY"]
        if key:
            if genai is None:
                errors["GEMINI_API_KEY"] = (
                    "Falta dependencia opcional 'google-generativeai'. "
                    "Instala requirements para validar claves de Gemini."
                )
            else:
                try:
                    genai.configure(api_key=key)
                    list(genai.list_models())
                except Exception as exc:
                    errors["GEMINI_API_KEY"] = f"Clave invalida: {exc}"

    if "GROQ_API_KEY" in changed_keys:
        key = data["GROQ_API_KEY"]
        if key:
            if Groq is None:
                errors["GROQ_API_KEY"] = (
                    "Falta dependencia opcional 'groq'. "
                    "Instala requirements para validar claves de Groq."
                )
            else:
                try:
                    client = Groq(api_key=key)
                    client.models.list()
                except Exception as exc:
                    errors["GROQ_API_KEY"] = f"Clave invalida: {exc}"

    return errors
