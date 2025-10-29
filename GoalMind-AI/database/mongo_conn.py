
"""

def init_app(app):
    app.config["MONGO_URI"] = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net/data"
    mongo.init_app(app)
    return mongo
"""

from flask_pymongo import PyMongo
from pymongo import MongoClient
import socket
import json

with open("database\mongo_user.json", "r", encoding="utf-8") as f:
    file = json.load(f)
username = file["username"]
pswd = file["pswd"]
collections = file["collections"]

mongo_local = PyMongo()
mongo_remote = None


def internet_available():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def init_app(app):
    """Inicializa las conexiones local y remota."""
    global mongo_remote

    # Conexión local
    app.config["MONGO_URI"] = "mongodb://localhost:27017/VirtualAssistantDB"
    mongo_local.init_app(app)
    print("Conectado a MongoDB local")

    # Conexión remota (solo si hay internet)
    if internet_available():
        print("🌐 Internet disponible → conectando a MongoDB Atlas...")
        uri_remote = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net/data"
        mongo_remote = MongoClient(uri_remote)
        app.mongo_remote = mongo_remote
        print("Conectado a MongoDB Atlas")
    else:
        app.mongo_remote = mongo_remote
        print("Sin conexión a internet → se usará solo la base local.")
    app.mongo_local = mongo_local
    return mongo_local, mongo_remote

def get_collection(name):
    """Devuelve referencias a las colecciones local y remota."""
    db_local = mongo_local.cx["VirtualAssistantDB"]
    db_remote = mongo_remote["data"] if mongo_remote else None
    return db_local[name], (db_remote[name] if db_remote is not None else None)


# ------------------------------------------------------
# 🧩 NUEVAS FUNCIONES DE SINCRONIZACIÓN UNITARIA
# ------------------------------------------------------

def sync_from_remote(collection_name, obj):
    """Comprueba si un documento existe en local; si no, lo descarga desde remoto."""
    local_col, remote_col = get_collection(collection_name)

    if not remote_col:
        print("⚠️ No hay conexión remota para sincronizar desde la nube.")
        return

    filtro = {"_id": obj["_id"]} if "_id" in obj else obj

    if not local_col.find_one(filtro):
        remoto = remote_col.find_one(filtro)
        if remoto:
            local_col.insert_one(remoto)
            print(f"⬇️ Documento {filtro} descargado desde la nube.")
        else:
            print("ℹ️ No existe en la nube.")


def sync_to_remote(collection_name, obj):
    """Comprueba si un documento existe en remoto; si no, lo sube."""
    local_col, remote_col = get_collection(collection_name)

    if not remote_col:
        print(" No hay conexión remota para subir datos.")
        return

    filtro = {"_id": obj["_id"]} if "_id" in obj else obj
    existe = remote_col.find_one(filtro)

    if not existe:
        remote_col.insert_one(obj)
        print(f"Documento {filtro} subido a la nube.")
    else:
        print("Documento ya existe en la nube.")

def sync_all_collections():
    """Sincroniza todas las colecciones desde la base remota hacia local."""
    from flask import current_app 

    remote = current_app.mongo_remote
    if remote is None:
        print("No hay conexión remota. No se sincronizan datos a la nube.")
        return

    for col in collections:
        local_col, remote_col = get_collection(col)
        if remote_col is not None:
            remote_docs = remote_col.find()
            for doc in remote_docs:
                # Descargar solo si no existe en local
                if not local_col.find_one({"_id": doc["_id"]}):
                    local_col.insert_one(doc)
                    print(f"⬇️ Sincronizado desde la nube → {col}: {doc['_id']}")
        else:
            print(f" No hay DB remota para sincronizar colección: {col}")
            
def sync_local_to_remote():
    """Sube a la nube los documentos que existan en local pero no en remoto."""

    from flask import current_app
    remote = current_app.mongo_remote

    if remote is None:
        print("⚠️ No hay conexión remota → no se puede sincronizar hacia la nube.")
        return

    for col in collections:
        local_col, remote_col = get_collection(col)

        if remote_col is None:
            print(f"⚠️ No hay colección remota para: {col}")
            continue

        print(f"🔼 Comprobando sincronización local → remoto para '{col}'...\n")

        for local_doc in local_col.find():
            sync_to_remote(col, local_doc)  # ✅ usando tu función existente

    print("\n✅ Sincronización local → remoto completada ✅")