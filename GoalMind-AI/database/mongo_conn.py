
### !!!!!!!!! Comprobar la lista de IP en MongoDB Atlas si hay problemas de conexión !!!!!!!!! ###

# Utilidades para manejo de rutas y archivos
from pathlib import Path

# Permite la conexion a la base de datos MongoDB via Flask-PyMongo (Local y Remota).
from flask_pymongo import PyMongo
from pymongo import MongoClient

# Módulo estándar de python para comprobar conexion a internet
import socket
# Módulo estándar de python para manejo de JSON
import json
# Certificados raíz (para evitar problemas TLS/SSL con Atlas en macOS, etc.) [si da error ejecutar en comandos: pip install certifi]
import certifi

############################### Configuracion de la base de datos MongoDB #############################
# Ruta al archivo JSON que contiene las credenciales de la base de datos remota
# El archivo mongo_user.json debe estar en la misma carpeta que este archivo
CONFIG_PATH = Path(__file__).resolve().parent / "mongo_user.json"

# Carga las credenciales desde la ruta configurada
with CONFIG_PATH.open("r", encoding="utf-8") as f:
    file = json.load(f)
    username = file["username"]
    pswd = file["pswd"]
    collections = file["collections"]

# Objetos de conexión
mongo_local = PyMongo()
mongo_remote = None


def internet_available():
    """Devuelve True si hay conexión a Internet, False en caso contrario."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def init_app(app):
    """Inicializa las conexiones local y remota (Atlas)."""
    global mongo_remote

    # ------------- CONEXIÓN LOCAL -------------
    app.config["MONGO_URI"] = "mongodb://127.0.0.1:27017/VirtualAssistantDB"
    mongo_local.init_app(app)
    app.mongo_local = mongo_local
    print("✅ Conectado a MongoDB local")

    # Por defecto asumimos que NO hay remoto
    mongo_remote = None
    app.mongo_remote = None

    # ------------- CONEXIÓN REMOTA (ATLAS) -------------
    if internet_available():
        print("🌐 Internet disponible → probando conexión a MongoDB Atlas...")
        uri_remote = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net/data"

        try:
            # Creamos el cliente con timeout y certificados de certifi
            client = MongoClient(
                uri_remote,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
            )
            # Forzamos un ping para comprobar que la conexión es válida
            client.admin.command("ping")

            mongo_remote = client
            app.mongo_remote = client
            print("✅ Conectado a MongoDB Atlas")
        except Exception as e:
            # Si falla el handshake SSL o cualquier otra cosa → seguimos solo con local
            mongo_remote = None
            app.mongo_remote = None
            print(f"⚠️ No se pudo conectar a Atlas, se usará SOLO la base local.\nDetalle: {e}")
    else:
        print("⚠️ Sin conexión a internet → se usará solo la base local.")

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
    """Sube o actualiza un documento en la base remota."""
    local_col, remote_col = get_collection(collection_name)

    if not remote_col:
        print("⚠️ No hay conexión remota para subir datos.")
        return

    if "_id" not in obj:
        print("⚠️ El documento no tiene _id, no se puede sincronizar.")
        return

    filtro = {"_id": obj["_id"]}

    # Usar replace_one con upsert=True para insertar o actualizar
    result = remote_col.replace_one(filtro, obj, upsert=True)

    if result.upserted_id:
        print(f"⬆️ Documento {filtro} subido a la nube.")
    elif result.modified_count > 0:
        print(f"🔄 Documento {filtro} actualizado en la nube.")
    else:
        print(f"ℹ️ Documento {filtro} sin cambios en la nube.")


def sync_all_collections():
    """Sincroniza todas las colecciones desde la base remota hacia local."""
    from flask import current_app

    remote = current_app.mongo_remote
    if remote is None:
        print("⚠️ No hay conexión remota. No se sincronizan datos desde la nube.")
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
            print(f"⚠️ No hay DB remota para sincronizar colección: {col}")


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
            sync_to_remote(col, local_doc)

    print("\n✅ Sincronización local → remoto completada ✅")
