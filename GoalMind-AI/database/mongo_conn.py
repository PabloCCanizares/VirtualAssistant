
### !!!!!!!!! Comprobar la lista de IP en MongoDB Atlas si hay problemas de conexión !!!!!!!!! ###

# Utilidades para manejo de rutas y archivos
import hashlib
import logging

# Módulo estándar de python para variables de entorno y hashing
import os

# Módulo estándar de python para comprobar conexion a internet
import socket
from pathlib import Path
from urllib.parse import urlparse

# Certificados raíz (para evitar problemas TLS/SSL con Atlas en macOS, etc.) [si da error ejecutar en comandos: pip install certifi]
import certifi
from bson import ObjectId

# Permite la conexion a la base de datos MongoDB via Flask-PyMongo (Local y Remota).
from flask import current_app
from flask_pymongo import PyMongo
from pymongo import MongoClient

from database.mongo_settings import load_mongo_settings, redact_mongo_uri
from services.mongo_sync_service import (
    SYNC_COLLECTIONS,
    _doc_timestamp,
    _find_by_id_variants,
    _id_variants,
    _parse_datetime,
    _remote_should_replace_local,
    flush_deletion_queue,
    get_pending_deletions,
    queue_deletion,
    sync_all_collections,
    sync_from_remote,
    sync_local_to_remote,
    sync_to_remote,
)

try:
    from dotenv import set_key as _dotenv_set_key
except ImportError:
    _dotenv_set_key = None  # type: ignore[assignment]

__all__ = [
    "ENV_PATH",
    "collections",
    "ensure_remote_connection",
    "extract_username_from_uri",
    "flush_deletion_queue",
    "generate_user_id_from_nickname",
    "get_app_user_id",
    "get_collection",
    "get_local_database",
    "get_pending_deletions",
    "get_remote_database",
    "init_app",
    "internet_available",
    "mongo_local",
    "mongo_remote",
    "queue_deletion",
    "reconnect_databases",
    "remote_uid_filter",
    "sync_all_collections",
    "sync_from_remote",
    "sync_local_to_remote",
    "sync_to_remote",
    "_doc_timestamp",
    "_find_by_id_variants",
    "_id_variants",
    "_parse_datetime",
    "_persist_user_nickname",
    "_remote_should_replace_local",
]

############################### Configuracion de la base de datos MongoDB #############################
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

# Objetos de conexión
mongo_local = PyMongo()
mongo_remote = None

# Nombres dinámicos de las bases de datos (se configuran en init_app desde .env)
_local_db_name = ""
_remote_db_name = ""

# Lista de colecciones para sincronización.
collections = list(SYNC_COLLECTIONS)
_configured_remote_uri = ""
logger = logging.getLogger(__name__)


def extract_username_from_uri(uri: str) -> str:
    """Extrae el username de una URI MongoDB (p.ej. 'dani' de 'mongodb+srv://dani:pass@host')."""
    if not uri:
        return ""
    try:
        return urlparse(uri).username or ""
    except Exception:
        return ""


def _persist_user_nickname(uri: str) -> None:
    """Deriva APP_USER_NICKNAME del username de la URI y lo persiste (best-effort)."""
    username = extract_username_from_uri(uri)
    if not username or os.getenv("APP_USER_NICKNAME") == username:
        return
    os.environ["APP_USER_NICKNAME"] = username
    if _dotenv_set_key is not None:
        try:
            _dotenv_set_key(str(ENV_PATH), "APP_USER_NICKNAME", username, quote_mode="never")
        except Exception:
            pass


def remote_uid_filter(usuario_id=None) -> dict:
    """Filtro remoto por usuario_id aceptando string u ObjectId."""
    uid = usuario_id or get_app_user_id()
    conditions = [{"usuario_id": uid}]
    try:
        if ObjectId.is_valid(str(uid)):
            conditions.append({"usuario_id": ObjectId(str(uid))})
    except Exception:
        pass
    return {"$or": conditions} if len(conditions) > 1 else conditions[0]


def generate_user_id_from_nickname(nickname: str) -> str:
    """Genera un ObjectId determinista (24 hex chars) desde un nickname."""
    digest = hashlib.sha256(nickname.strip().lower().encode("utf-8")).hexdigest()
    return digest[:24]  # 12 bytes = 24 hex chars = formato ObjectId válido


def get_app_user_id() -> str:
    """Devuelve el user ID activo: generado desde nickname o DEFAULT_USER_ID."""
    nickname = (os.getenv("APP_USER_NICKNAME") or "").strip()
    if not nickname or nickname.lower() == "shared_user":
        return "66ffbbbbbbbbbbbbbbbb0100"
    return generate_user_id_from_nickname(nickname)


def _create_mongo_client(uri: str) -> MongoClient:
    """Crea y valida un cliente MongoClient con TLS y timeout."""
    client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


def internet_available():
    """Devuelve True si hay conexión a Internet, False en caso contrario."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def init_app(app):
    """Inicializa las conexiones local y remota (Atlas)."""
    global mongo_remote, _local_db_name, _remote_db_name, _configured_remote_uri

    # ------------- LEER CONFIGURACIÓN -------------
    settings = load_mongo_settings()
    _local_db_name = settings.local_db
    _remote_db_name = settings.remote_db
    _configured_remote_uri = settings.remote_uri
    _persist_user_nickname(settings.remote_uri)

    # ------------- CONEXIÓN LOCAL -------------
    app.config["MONGO_URI"] = settings.local_connection_uri
    mongo_local.init_app(app)
    app.mongo_local = mongo_local
    print("Conectado a MongoDB local")

    # Por defecto asumimos que NO hay remoto
    mongo_remote = None
    app.mongo_remote = None

    # ------------- CONEXIÓN REMOTA (ATLAS) -------------
    if settings.remote_configured and internet_available():
        print("Internet disponible - probando conexion a MongoDB Atlas...")

        try:
            client = _create_mongo_client(settings.remote_uri)
            mongo_remote = client
            app.mongo_remote = client
            print("Conectado a MongoDB Atlas")
        except Exception as e:
            # Si falla el handshake SSL o cualquier otra cosa → seguimos solo con local
            mongo_remote = None
            app.mongo_remote = None
            print(f"No se pudo conectar a Atlas, se usará SOLO la base local.\nDetalle: {e}")
    elif not settings.remote_configured:
        print("Sin URI remota configurada → se usará solo la base local.")
    else:
        print("Sin conexión a internet → se usará solo la base local.")

    return mongo_local, mongo_remote


def ensure_remote_connection(app=None):
    """
    Intenta recuperar conexión remota si no existe.
    Devuelve True si hay remoto disponible, False en caso contrario.
    """
    global mongo_remote

    if mongo_remote is not None:
        if app is not None:
            app.mongo_remote = mongo_remote
        return True

    settings = load_mongo_settings()
    remote_uri = (_configured_remote_uri or settings.remote_uri).strip()
    if not remote_uri:
        return False

    if not internet_available():
        return False

    try:
        mongo_remote = _create_mongo_client(remote_uri)
        if app is not None:
            app.mongo_remote = mongo_remote
        logger.info("Reconexión a MongoDB Atlas completada.")
        return True
    except Exception as exc:
        logger.warning("No se pudo reconectar a MongoDB Atlas: %s", exc)
        return False


def reconnect_databases(app=None):
    """Reinicializa conexiones MongoDB con los valores actuales de os.environ."""
    global mongo_remote, _local_db_name, _remote_db_name, _configured_remote_uri

    if app is None:
        app = current_app

    errors = []
    local_ok = False
    remote_ok = False

    settings = load_mongo_settings()

    # --- Local ---
    try:
        old_client = mongo_local.cx
        new_client = MongoClient(settings.local_connection_uri)
        new_client.admin.command("ping")
        old_client.close()
        mongo_local.cx = new_client
        _local_db_name = settings.local_db
        app.config["MONGO_URI"] = settings.local_connection_uri
        app.mongo_local = mongo_local
        local_ok = True
        logger.info(
            "Reconexion local completada: %s",
            redact_mongo_uri(settings.local_connection_uri),
        )
    except Exception as exc:
        errors.append(f"MONGO_LOCAL_URI: {exc}")
        logger.warning("Fallo reconexion local: %s", exc)

    # --- Remoto ---
    if settings.remote_configured:
        try:
            if mongo_remote is not None:
                mongo_remote.close()
            client = _create_mongo_client(settings.remote_uri)
            mongo_remote = client
            _remote_db_name = settings.remote_db
            _configured_remote_uri = settings.remote_uri
            app.mongo_remote = mongo_remote
            remote_ok = True
            logger.info("Reconexion remota completada: %s", settings.remote_db)
            _persist_user_nickname(settings.remote_uri)
        except Exception as exc:
            mongo_remote = None
            app.mongo_remote = None
            errors.append(f"MONGO_REMOTE_URI: {exc}")
            logger.warning("Fallo reconexion remota: %s", exc)
    else:
        if mongo_remote is not None:
            mongo_remote.close()
        mongo_remote = None
        _configured_remote_uri = ""
        app.mongo_remote = None
        remote_ok = True

    return {"local": local_ok, "remote": remote_ok, "errors": errors}


def get_collection(name):
    """Devuelve referencias a las colecciones local y remota."""
    db_local = mongo_local.cx[_local_db_name]
    db_remote = mongo_remote[_remote_db_name] if mongo_remote else None
    return db_local[name], (db_remote[name] if db_remote is not None else None)


def get_local_database():
    """Devuelve la base de datos local activa."""
    return mongo_local.cx[_local_db_name]


def get_remote_database(app=None):
    """Devuelve la base de datos remota si está disponible."""
    if not ensure_remote_connection(app):
        return None
    return mongo_remote[_remote_db_name] if mongo_remote else None
