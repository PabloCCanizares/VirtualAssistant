
### !!!!!!!!! Comprobar la lista de IP en MongoDB Atlas si hay problemas de conexión !!!!!!!!! ###

import hashlib
import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import certifi
from bson import ObjectId
from flask_pymongo import PyMongo
from pymongo import MongoClient

############################### Configuracion de la base de datos MongoDB #############################
# Ruta al archivo JSON que contiene las credenciales de la base de datos remota (fallback)
CONFIG_PATH = Path(__file__).resolve().parent / "mongo_user.json"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

# Objetos de conexión
mongo_local = PyMongo()
mongo_remote = None

# Nombres dinámicos de las bases de datos (se configuran en init_app)
_local_db_name = "VirtualAssistantDB"
_remote_db_name = "VirtualAssistantDB"

# Lista de colecciones para sincronización
collections = [
    "Tasks",
    "Goals",
    "Projects",
    "ProjectDocuments",
    "ProjectDocumentFolders",
    "DailyMetrics",
    "Events",
    "PlanningSessions",
]
_configured_remote_uri = ""
logger = logging.getLogger(__name__)


def generate_user_id_from_nickname(nickname: str) -> str:
    """Genera un ObjectId determinista (24 hex chars) desde un nickname."""
    digest = hashlib.sha256(nickname.strip().lower().encode("utf-8")).hexdigest()
    return digest[:24]  # 12 bytes = 24 hex chars = formato ObjectId válido


def extract_username_from_uri(uri: str) -> str:
    """Extrae el usuario de una URI de Mongo, si existe."""
    try:
        return urlparse(uri or "").username or ""
    except Exception:
        return ""


def get_app_user_id() -> str:
    """Devuelve el user ID activo configurado para la app."""
    explicit_user_id = (os.getenv("APP_USER_ID") or "").strip()
    if explicit_user_id:
        return explicit_user_id

    nickname = (os.getenv("APP_USER_NICKNAME") or "").strip()
    if nickname and nickname != "shared_user":
        return generate_user_id_from_nickname(nickname)

    default_user_id = (os.getenv("DEFAULT_USER_ID") or "").strip()
    if default_user_id:
        return default_user_id

    remote_username = extract_username_from_uri(os.getenv("MONGO_REMOTE_URI", ""))
    if remote_username and remote_username != "shared_user":
        return generate_user_id_from_nickname(remote_username)

    return "66ffbbbbbbbbbbbbbbbb0100"


def remote_uid_filter(usuario_id=None):
    """Filtro robusto para IDs guardados como string u ObjectId."""
    uid = usuario_id or get_app_user_id()
    variants = _id_variants(uid)
    if len(variants) == 1:
        return {"usuario_id": variants[0]}
    return {"$or": [{"usuario_id": variant} for variant in variants]}


def internet_available():
    """Devuelve True si hay conexión a Internet, False en caso contrario."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def _create_mongo_client(uri: str):
    kwargs = {"serverSelectionTimeoutMS": 5000}
    if str(uri).startswith("mongodb+srv://"):
        kwargs["tlsCAFile"] = certifi.where()
    return MongoClient(uri, **kwargs)


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None
    return None


def _doc_timestamp(doc):
    if not isinstance(doc, dict):
        return None
    for key in ("updated_at", "fecha_modificacion", "modified_at", "fecha_creacion", "created_at"):
        ts = _parse_datetime(doc.get(key))
        if ts is not None:
            return ts
    return None


def _remote_should_replace_local(local_doc, remote_doc) -> bool:
    if not local_doc:
        return True
    local_ts = _doc_timestamp(local_doc)
    remote_ts = _doc_timestamp(remote_doc)
    if remote_ts and local_ts:
        return remote_ts > local_ts
    if remote_ts and not local_ts:
        return True
    if local_ts and not remote_ts:
        return False
    return local_doc != remote_doc


def _id_variants(value):
    candidates = []
    if isinstance(value, ObjectId):
        candidates.extend([value, str(value)])
    else:
        candidates.append(value)
        try:
            if ObjectId.is_valid(str(value)):
                candidates.append(ObjectId(str(value)))
        except Exception:
            pass

    seen = set()
    variants = []
    for candidate in candidates:
        key = (type(candidate).__name__, str(candidate))
        if key in seen:
            continue
        seen.add(key)
        variants.append(candidate)
    return variants


def _find_by_id_variants(collection, value):
    for candidate in _id_variants(value):
        found = collection.find_one({"_id": candidate})
        if found is not None:
            return found
    return None


def _id_lookup_key(value):
    return (type(value).__name__, str(value))


def _build_id_doc_map(documents):
    doc_map = {}
    for doc in documents:
        if "_id" in doc:
            doc_map[_id_lookup_key(doc["_id"])] = doc
    return doc_map


def _find_in_id_doc_map(doc_map, value):
    for candidate in _id_variants(value):
        found = doc_map.get(_id_lookup_key(candidate))
        if found is not None:
            return found
    return None


def get_local_database():
    """Devuelve la base local activa."""
    try:
        return mongo_local.cx[_local_db_name]
    except Exception:
        return None


def get_remote_database(app=None):
    """Devuelve la base remota activa, si existe."""
    remote = mongo_remote
    if remote is None and app is not None:
        remote = getattr(app, "mongo_remote", None)
    if remote is None:
        return None
    try:
        return remote[_remote_db_name]
    except Exception:
        return None


def _persist_user_nickname(remote_uri: str) -> None:
    nickname = extract_username_from_uri(remote_uri)
    if not nickname:
        return
    if (os.getenv("APP_USER_NICKNAME") or "").strip() == nickname:
        return
    os.environ["APP_USER_NICKNAME"] = nickname


def reconnect_databases(app=None):
    """Reconecta las bases usando las variables actuales de entorno."""
    global mongo_remote, _local_db_name, _remote_db_name, _configured_remote_uri

    result = {"local": False, "remote": False, "errors": []}

    local_uri = os.getenv("MONGO_LOCAL_URI", "mongodb://127.0.0.1:27017")
    _local_db_name = os.getenv("MONGO_LOCAL_DB", "VirtualAssistantDB")
    remote_uri = (os.getenv("MONGO_REMOTE_URI") or "").strip()
    _remote_db_name = os.getenv("MONGO_REMOTE_DB", "VirtualAssistantDB")
    _configured_remote_uri = remote_uri

    try:
        local_client = _create_mongo_client(local_uri)
        try:
            local_client.admin.command("ping")
        except Exception:
            # mongomock y algunos clientes de test no implementan ping igual que PyMongo.
            pass
        mongo_local.cx = local_client
        if app is not None:
            app.mongo_local = mongo_local
            app.config["MONGO_URI"] = f"{local_uri}/{_local_db_name}"
        result["local"] = True
    except Exception as exc:
        result["errors"].append(f"Local MongoDB: {exc}")

    if not remote_uri:
        mongo_remote = None
        if app is not None:
            app.mongo_remote = None
        result["remote"] = True
        return result

    try:
        remote_client = _create_mongo_client(remote_uri)
        try:
            remote_client.admin.command("ping")
        except Exception:
            pass
        mongo_remote = remote_client
        if app is not None:
            app.mongo_remote = remote_client
        _persist_user_nickname(remote_uri)
        result["remote"] = True
    except Exception as exc:
        mongo_remote = None
        if app is not None:
            app.mongo_remote = None
        result["errors"].append(f"MongoDB remoto: {exc}")

    return result


def init_app(app):
    """Inicializa las conexiones local y remota (Atlas)."""
    global mongo_remote, _local_db_name, _remote_db_name, collections, _configured_remote_uri

    # ------------- LEER CONFIGURACIÓN (env vars > mongo_user.json > defaults) -------------
    local_uri = os.getenv("MONGO_LOCAL_URI", "mongodb://127.0.0.1:27017")
    _local_db_name = os.getenv("MONGO_LOCAL_DB", "VirtualAssistantDB")
    remote_uri = (os.getenv("MONGO_REMOTE_URI") or "").strip()
    _remote_db_name = os.getenv("MONGO_REMOTE_DB", "VirtualAssistantDB")

    # Fallback: si no hay MONGO_REMOTE_URI, intentar leer de mongo_user.json
    if not remote_uri:
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                file = json.load(f)
            username = file["username"]
            pswd = file["pswd"]
            remote_uri = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net"
            # Actualizar colecciones desde el archivo si existen
            if "collections" in file:
                collections = file["collections"]
        except Exception:
            remote_uri = ""
    _configured_remote_uri = remote_uri

    # ------------- CONEXIÓN LOCAL -------------
    app.config["MONGO_URI"] = f"{local_uri}/{_local_db_name}"
    mongo_local.init_app(app)
    app.mongo_local = mongo_local
    print("Conectado a MongoDB local")

    # Por defecto asumimos que NO hay remoto
    mongo_remote = None
    app.mongo_remote = None

    # ------------- CONEXIÓN REMOTA (ATLAS) -------------
    if remote_uri and internet_available():
        print("Internet disponible → probando conexión a MongoDB Atlas...")

        try:
            # Creamos el cliente con timeout y certificados de certifi
            client = MongoClient(
                remote_uri,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
            )
            # Forzamos un ping para comprobar que la conexión es válida
            client.admin.command("ping")

            mongo_remote = client
            app.mongo_remote = client
            _persist_user_nickname(remote_uri)
            print("Conectado a MongoDB Atlas")
        except Exception as e:
            # Si falla el handshake SSL o cualquier otra cosa → seguimos solo con local
            mongo_remote = None
            app.mongo_remote = None
            print(f"No se pudo conectar a Atlas, se usará SOLO la base local.\nDetalle: {e}")
    elif not remote_uri:
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

    remote_uri = (_configured_remote_uri or os.getenv("MONGO_REMOTE_URI", "")).strip()
    if not remote_uri:
        return False

    if not internet_available():
        return False

    try:
        client = _create_mongo_client(remote_uri)
        client.admin.command("ping")
        mongo_remote = client
        if app is not None:
            app.mongo_remote = client
        logger.info("Reconexión a MongoDB Atlas completada.")
        return True
    except Exception as exc:
        logger.warning("No se pudo reconectar a MongoDB Atlas: %s", exc)
        return False


def get_collection(name):
    """Devuelve referencias a las colecciones local y remota."""
    db_local = mongo_local.cx[_local_db_name]
    db_remote = mongo_remote[_remote_db_name] if mongo_remote else None
    return db_local[name], (db_remote[name] if db_remote is not None else None)


# ------------------------------------------------------
# 🧩 NUEVAS FUNCIONES DE SINCRONIZACIÓN UNITARIA
# ------------------------------------------------------

def sync_from_remote(collection_name, obj):
    """Comprueba si un documento existe en local; si no, lo descarga desde remoto."""
    local_col, remote_col = get_collection(collection_name)

    if remote_col is None:
        return

    filtro = {"_id": obj["_id"]} if "_id" in obj else obj

    if not local_col.find_one(filtro):
        remoto = remote_col.find_one(filtro)
        if remoto:
            local_col.insert_one(remoto)


def sync_to_remote(collection_name, obj):
    """Sube o actualiza un documento en la base remota."""
    _, remote_col = get_collection(collection_name)

    if remote_col is None:
        return False

    if "_id" not in obj:
        return False

    doc = dict(obj)
    if collection_name == "ProjectDocuments" and doc.get("remote_sync_pending"):
        return False
    if collection_name == "ProjectDocuments" and doc.get("upload_id"):
        doc.pop("local_upload_id", None)

    filtro = {"_id": doc["_id"]}

    # Usar replace_one con upsert=True para insertar o actualizar
    remote_col.replace_one(filtro, doc, upsert=True)
    return True


def sync_all_collections():
    """Sincroniza todas las colecciones desde la base remota hacia local."""
    from flask import current_app, has_app_context

    app = current_app if has_app_context() else None
    if not ensure_remote_connection(app):
        return 0

    pulled_docs = 0
    for col in collections:
        pending_ids = get_pending_deletions(col)
        local_col, remote_col = get_collection(col)
        if remote_col is not None:
            if pending_ids:
                object_ids = []
                string_ids = []
                for pid in pending_ids:
                    try:
                        if ObjectId.is_valid(str(pid)):
                            object_ids.append(ObjectId(str(pid)))
                        else:
                            string_ids.append(str(pid))
                    except Exception:
                        string_ids.append(str(pid))

                delete_query = {"$or": []}
                if object_ids:
                    delete_query["$or"].append({"_id": {"$in": object_ids}})
                if string_ids:
                    delete_query["$or"].append({"_id": {"$in": string_ids}})
                if delete_query["$or"]:
                    local_col.delete_many(delete_query)

            remote_docs = remote_col.find()
            for doc in remote_docs:
                if str(doc.get("_id")) in pending_ids:
                    continue
                local_doc = _find_by_id_variants(local_col, doc.get("_id"))
                if local_doc is None:
                    local_col.insert_one(doc)
                    pulled_docs += 1
                elif _remote_should_replace_local(local_doc, doc):
                    local_col.replace_one({"_id": local_doc["_id"]}, doc)
                    pulled_docs += 1
    return pulled_docs


def sync_local_to_remote():
    """Sube a la nube los documentos que existan en local pero no en remoto."""
    from flask import current_app, has_app_context

    app = current_app if has_app_context() else None
    if not ensure_remote_connection(app):
        return 0

    pushed_docs = 0
    for col in collections:
        local_col, remote_col = get_collection(col)
        pending_ids = get_pending_deletions(col)

        if remote_col is None:
            continue
        remote_doc_map = _build_id_doc_map(remote_col.find())
        for local_doc in local_col.find():
            if str(local_doc.get("_id")) in pending_ids:
                continue
            if col == "ProjectDocuments" and local_doc.get("remote_sync_pending"):
                continue
            remote_doc = _find_in_id_doc_map(remote_doc_map, local_doc.get("_id"))
            doc_to_push = dict(local_doc)
            if col == "ProjectDocuments" and doc_to_push.get("upload_id"):
                doc_to_push.pop("local_upload_id", None)
            if remote_doc is not None:
                if _remote_should_replace_local(doc_to_push, remote_doc):
                    continue
                if remote_doc == doc_to_push:
                    continue
            remote_filter = {"_id": remote_doc["_id"]} if remote_doc else {"_id": doc_to_push["_id"]}
            remote_col.replace_one(remote_filter, doc_to_push, upsert=True)
            remote_doc_map[_id_lookup_key(doc_to_push["_id"])] = doc_to_push
            pushed_docs += 1
    return pushed_docs


def queue_deletion(collection_name, target_id):
    """Guarda en cola una eliminación para sincronizar cuando haya conexión remota."""
    local_col, _ = get_collection("DeleteQueue")
    if not collection_name:
        return False
    if target_id is None:
        return False

    target_id_str = str(target_id)
    try:
        if ObjectId.is_valid(target_id_str):
            target_id_str = str(ObjectId(target_id_str))
    except Exception:
        pass

    queue_id = f"{collection_name}:{target_id_str}"

    payload = {
        "_id": queue_id,
        "collection": collection_name,
        "target_id": target_id_str,
        "deleted_at": datetime.utcnow(),
    }

    try:
        local_col.update_one({"_id": queue_id}, {"$setOnInsert": payload}, upsert=True)
        # Asegurar que el documento se elimine localmente (por si se reinsertó)
        target_local, _ = get_collection(collection_name)
        queries = [{"_id": target_id_str}]
        try:
            if ObjectId.is_valid(target_id_str):
                queries.append({"_id": ObjectId(target_id_str)})
        except Exception:
            pass
        if queries:
            target_local.delete_many({"$or": queries})
        return True
    except Exception:
        return False


def get_pending_deletions(collection_name):
    """Devuelve un set con los IDs pendientes de eliminar para una colección."""
    local_col, _ = get_collection("DeleteQueue")
    pending = set()
    for doc in local_col.find({"collection": collection_name}):
        pending_id = doc.get("target_id", doc.get("_id"))
        if pending_id is not None:
            pending.add(str(pending_id))
    return pending


def flush_deletion_queue():
    """Intenta eliminar en remoto los documentos en cola y limpia los completados."""
    local_col, _ = get_collection("DeleteQueue")
    if not ensure_remote_connection():
        return 0

    removed = 0
    for item in local_col.find().sort("deleted_at", 1):
        collection = item.get("collection")
        target_id = item.get("target_id", item.get("_id"))
        if not collection or target_id is None:
            continue

        _, remote_col = get_collection(collection)
        if remote_col is None:
            continue

        # Intentar eliminar con ambas representaciones (ObjectId y string)
        candidates = []
        if isinstance(target_id, ObjectId):
            candidates.append(target_id)
            candidates.append(str(target_id))
        else:
            candidates.append(target_id)
            try:
                if ObjectId.is_valid(str(target_id)):
                    candidates.append(ObjectId(str(target_id)))
            except Exception:
                pass

        # Deduplicar manteniendo orden
        seen = set()
        unique_candidates = []
        for cid in candidates:
            key = (type(cid).__name__, str(cid))
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(cid)

        delete_query = {"$or": [{"_id": cid} for cid in unique_candidates]}
        deleted = 0
        delete_error = False
        try:
            deleted = remote_col.delete_many(delete_query).deleted_count
        except Exception:
            deleted = 0
            delete_error = True

        if deleted > 0:
            local_col.delete_one({"_id": item["_id"]})
            removed += 1
            continue

        # Si hubo error o no se pudo confirmar el borrado, mantener en cola
        if delete_error:
            continue

        # Si no se eliminó, mantener en cola para reintentar más tarde
        continue

    return removed
