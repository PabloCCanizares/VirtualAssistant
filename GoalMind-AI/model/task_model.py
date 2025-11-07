from database.mongo_conn import get_collection, sync_to_remote, sync_from_remote
from bson import ObjectId
from datetime import datetime


class TaskModel:
    """Gestión de la colección 'tasks' con sincronización local/remota."""

    COLLECTION = "Tasks"

    # -------------------------------------------------------------
    #  INSERTAR
    # -------------------------------------------------------------
    @staticmethod
    def insert_task(task_data):
        """
        Inserta una tarea en la base local y la sincroniza con la remota si está disponible.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)

        # Asegurar que tenga fecha de creación
        if "fecha_creacion" not in task_data:
            task_data["fecha_creacion"] = datetime.utcnow()

        # Insertar en local
        result = local_col.insert_one(task_data)
        task_data["_id"] = result.inserted_id

        # Sincronizar con la nube
        sync_to_remote(TaskModel.COLLECTION, task_data)

        print(f"🗂️ Tarea insertada localmente y sincronizada: {task_data['_id']}")
        return task_data
    

    # -------------------------------------------------------------
    #  OBTENER POR ID
    # -------------------------------------------------------------
    @staticmethod
    def get_task_by_id(task_id):
        """
        Obtiene una tarea por su _id.
        Si no está en local, intenta descargarla desde la remota.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        task = local_col.find_one({"_id": _id})

        if not task:
            sync_from_remote(TaskModel.COLLECTION, {"_id": _id})
            task = local_col.find_one({"_id": _id})

        return task
    
        # -------------------------------------------------------------
    #  OBTENER POR CATEGORÍA
    # -------------------------------------------------------------
    @staticmethod
    def get_tasks_by_category(categoria):
        """
        Devuelve todas las tareas de una categoría específica.
        
        Args:
            categoria (str): Categoría a filtrar (ej: "trabajo", "personal", "estudio")
            
        Returns:
            list: Lista de tareas que pertenecen a la categoría especificada
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        
        # Buscar tareas por categoría, ordenadas por fecha de creación descendente
        return list(local_col.find({"categoria": categoria}).sort("fecha_creacion", -1))

    # -------------------------------------------------------------
    #  OBTENER TODAS
    # -------------------------------------------------------------
    @staticmethod
    def get_all_tasks():
        """
        Devuelve todas las tareas almacenadas localmente.
        (No descarga desde remoto automáticamente.)
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        return list(local_col.find())

    # -------------------------------------------------------------
    #  OBTENER POR USUARIO
    # -------------------------------------------------------------
    @staticmethod
    def get_task_by_user(usuario_id):
        """
        Devuelve todas las tareas de un usuario específico.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(usuario_id) if not isinstance(usuario_id, ObjectId) else usuario_id
        return list(local_col.find({"usuario_id": _id}))

    # -------------------------------------------------------------
    #  ELIMINAR
    # -------------------------------------------------------------
    @staticmethod
    def delete_task(task_id):
        """
        Elimina una tarea tanto en la base local como remota (si está disponible).
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        # Eliminar local
        local_col.delete_one({"_id": _id})

        # Eliminar remoto (si hay conexión)
        if remote_col:
            remote_col.delete_one({"_id": _id})
            print(f"🗑️ Tarea eliminada en local y remoto: {_id}")
        else:
            print(f"⚠️ Tarea eliminada solo localmente (sin conexión remota): {_id}")

    # -------------------------------------------------------------
    #  ACTUALIZAR
    # -------------------------------------------------------------
    @staticmethod
    def update_task(task_id, updates):
        """
        Actualiza una tarea localmente y sincroniza los cambios con la base remota.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        # Actualizar en local
        local_col.update_one({"_id": _id}, {"$set": updates})

        # Obtener el documento actualizado
        updated_task = local_col.find_one({"_id": _id})

        # Sincronizar con la nube
        sync_to_remote(TaskModel.COLLECTION, updated_task)

        print(f"♻️ Tarea {_id} actualizada y sincronizada.")
        return updated_task
    
    


# -------------------------------------------------------------
#  CONSULTAS 07-11-2025
# -------------------------------------------------------------
@staticmethod
def get_all_tasks():
    """Devuelve todas las tareas desde la base local."""
    local_col, _ = get_collection(TaskModel.COLLECTION)
    return list(local_col.find().sort("fecha_creacion", -1))

@staticmethod
def get_task_by_id(task_id):
    """Obtiene una tarea por su _id."""
    local_col, _ = get_collection(TaskModel.COLLECTION)
    _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id
    return local_col.find_one({"_id": _id})


