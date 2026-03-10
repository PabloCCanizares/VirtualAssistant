
### !!!!!!!!! Comprobar la lista de IP en MongoDB Atlas si hay problemas de conexión !!!!!!!!! ###

# Utilidades para manejo de rutas y archivos
from pathlib import Path

# Permite la conexion a la base de datos MongoDB via Flask-PyMongo (Local y Remota).
from flask_pymongo import PyMongo
from pymongo import MongoClient, ReplaceOne
import logging

# Módulo estándar de python para comprobar conexion a internet
import socket
# Módulo estándar de python para manejo de JSON
import json
# Módulo estándar de python para variables de entorno y hashing
import os
import hashlib
# Certificados raíz (para evitar problemas TLS/SSL con Atlas en macOS, etc.) [si da error ejecutar en comandos: pip install certifi]
import certifi
from datetime import datetime
from bson import ObjectId

############################### Configuracion de la base de datos MongoDB #############################
# Ruta al archivo JSON que contiene las credenciales de la base de datos remota (fallback)
CONFIG_PATH = Path(__file__).resolve().parent / "mongo_user.json"

# Objetos de conexión
mongo_local = PyMongo()
mongo_remote = None

# Nombres dinámicos de las bases de datos (se configuran en init_app desde .env)
_local_db_name = ""
_remote_db_name = ""

# Lista de colecciones para sincronización
collections = ["Tasks", "Goals", "Projects", "ProjectDocuments", "Events"]
_configured_remote_uri = ""
logger = logging.getLogger(__name__)


def generate_user_id_from_nickname(nickname: str) -> str:
    """Genera un ObjectId determinista (24 hex chars) desde un nickname."""
    digest = hashlib.sha256(nickname.strip().lower().encode("utf-8")).hexdigest()
    return digest[:24]  # 12 bytes = 24 hex chars = formato ObjectId válido


def get_app_user_id() -> str:
    """Devuelve el user ID activo: generado desde nickname o DEFAULT_USER_ID."""
    nickname = (os.getenv("APP_USER_NICKNAME") or "").strip()
    if nickname:
        return generate_user_id_from_nickname(nickname)
    return os.getenv("DEFAULT_USER_ID", "66ffbbbbbbbbbbbbbbbb0100")


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
            client = _create_mongo_client(remote_uri)
            mongo_remote = client
            app.mongo_remote = client
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
        mongo_remote = _create_mongo_client(remote_uri)
        if app is not None:
            app.mongo_remote = mongo_remote
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
# FUNCIONES DE SINCRONIZACIÓN UNITARIA
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

    filtro = {"_id": obj["_id"]}

    # Usar replace_one con upsert=True para insertar o actualizar
    remote_col.replace_one(filtro, obj, upsert=True)
    return True


def sync_all_collections():
    """Sincroniza todas las colecciones desde la base remota hacia local."""
    from flask import current_app

    if not ensure_remote_connection(current_app):
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

            existing_ids = {doc["_id"] for doc in local_col.find({}, {"_id": 1})}
            new_docs = [
                doc for doc in remote_col.find()
                if doc["_id"] not in existing_ids and str(doc.get("_id")) not in pending_ids
            ]
            if new_docs:
                local_col.insert_many(new_docs)
                pulled_docs += len(new_docs)
    return pulled_docs


def sync_local_to_remote():
    """Sube a la nube los documentos que existan en local pero no en remoto."""
    from flask import current_app

    if not ensure_remote_connection(current_app):
        return 0

    pushed_docs = 0
    for col in collections:
        local_col, remote_col = get_collection(col)
        pending_ids = get_pending_deletions(col)

        if remote_col is None:
            continue
        ops = [
            ReplaceOne({"_id": doc["_id"]}, doc, upsert=True)
            for doc in local_col.find()
            if str(doc.get("_id")) not in pending_ids
        ]
        if ops:
            remote_col.bulk_write(ops)
            pushed_docs += len(ops)
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
            key = str(cid)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(cid)

        delete_query = {"$or": [{"_id": cid} for cid in unique_candidates]}
        try:
            deleted = remote_col.delete_many(delete_query).deleted_count
        except Exception:
            continue

        if deleted > 0:
            local_col.delete_one({"_id": item["_id"]})
            removed += 1

    return removed
