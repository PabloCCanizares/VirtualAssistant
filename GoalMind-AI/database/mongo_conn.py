
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
    print("💾 Conectado a MongoDB local")

    # Conexión remota (solo si hay internet)
    if internet_available():
        print("🌐 Internet disponible → conectando a MongoDB Atlas...")
        uri_remote = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net/data"
        mongo_remote = MongoClient(uri_remote)
        print("✅ Conectado a MongoDB Atlas")
    else:
        print("⚠️ Sin conexión a internet → se usará solo la base local.")

    return mongo_local, mongo_remote

def get_collection(name):
    """Devuelve referencias a las colecciones local y remota."""
    db_local = mongo_local.cx["VirtualAssistantDB"]
    db_remote = mongo_remote["data"] if mongo_remote else None
    return db_local[name], db_remote[name] if db_remote else None


# ------------------------------------------------------
# 🧩 NUEVAS FUNCIONES DE SINCRONIZACIÓN UNITARIA
# ------------------------------------------------------

def sync_from_remote(collection_name, obj):
    """Comprueba si un documento existe en local; si no, lo descarga desde remoto."""
    local_col, remote_col = get_collection(collection_name)

    if not remote_col:
        print("⚠️ No hay conexión remota para sincronizar desde la nube.")
        return

    # Buscar por ID o clave única
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
        print("⚠️ No hay conexión remota para subir datos.")
        return

    filtro = {"_id": obj["_id"]} if "_id" in obj else obj
    existe = remote_col.find_one(filtro)

    if not existe:
        remote_col.insert_one(obj)
        print(f"⬆️ Documento {filtro} subido a la nube.")
    else:
        print("✅ Documento ya existe en la nube.")
