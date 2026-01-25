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
    def get_tasks_by_category(category_id):
        """
        Devuelve todas las tareas que contengan una categoría específica.
        
        Args:
            category_id: ObjectId o string del ID de la categoría
            
        Returns:
            list: Lista de tareas que pertenecen a la categoría especificada
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        
        # Buscar tareas que contengan esta categoría en su array de categorías
        return list(local_col.find({"categorias": _id}).sort("fecha_creacion", -1))

    # -------------------------------------------------------------
    #  BUSCAR TAREAS POR NOMBRE Y/O CATEGORÍA
    # -------------------------------------------------------------
    @staticmethod
    def search_tasks(nombre=None, categoria=None, category_ids=None):
        """
        Busca tareas por nombre (contenido) y/o categoría.
        La búsqueda por nombre es case-insensitive y parcial (regex).
        No filtra por usuario, devuelve todas las tareas que coincidan.
        
        Args:
            nombre (str): Texto a buscar en el campo 'contenido' (opcional)
            categoria (str): Texto para buscar en nombres de categorías - DEPRECADO, usar category_ids
            category_ids (list): Lista de IDs de categorías para filtrar (opcional)
            
        Returns:
            list: Lista de tareas que coinciden con los criterios
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        
        # Construir query dinámicamente
        query = {}
        
        # Filtro por nombre (búsqueda parcial case-insensitive)
        if nombre and nombre.strip():
            query["contenido"] = {"$regex": nombre.strip(), "$options": "i"}
        
        # Filtro por categorías (array de ObjectIds)
        if category_ids and len(category_ids) > 0:
            # Convertir a ObjectIds si es necesario
            cat_oids = []
            for cid in category_ids:
                try:
                    if isinstance(cid, ObjectId):
                        cat_oids.append(cid)
                    else:
                        cat_oids.append(ObjectId(str(cid)))
                except Exception:
                    continue
            if cat_oids:
                # Buscar tareas que tengan al menos una de las categorías
                query["categorias"] = {"$in": cat_oids}
        
        # Si no hay filtros, devolver todas las tareas
        if not query:
            return list(local_col.find().sort("fecha_creacion", -1))
        
        return list(local_col.find(query).sort("fecha_creacion", -1))

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
    #  OBTENER POR OBJETIVO (GOAL)
    # -------------------------------------------------------------
    @staticmethod
    def get_tasks_by_goal(goal_id):
        """
        Devuelve todas las tareas asociadas a un objetivo específico.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        return list(local_col.find({"goal_id": _id}).sort("fecha_creacion", -1))

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

    @staticmethod
    def delete_tasks_by_ids(task_ids):
        """
        Elimina varias tareas por sus _id. Devuelve el nº de documentos eliminados.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        ids = [
            ObjectId(tid) if not isinstance(tid, ObjectId) else tid
            for tid in task_ids if tid
        ]
        res_local = local_col.delete_many({"_id": {"$in": ids}})

        if remote_col is not None:
            try:
                remote_col.delete_many({"_id": {"$in": ids}})
            except Exception:
                pass

        return res_local.deleted_count

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
    #  ASIGNAR OBJETIVO A MÚLTIPLES TAREAS
    # -------------------------------------------------------------
    @staticmethod
    def assign_goal_to_tasks(task_ids, goal_id):
        """
        Asigna un objetivo (goal_id) a múltiples tareas.
        Devuelve el número de tareas actualizadas.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        
        # Convertir IDs a ObjectId
        object_ids = [
            ObjectId(tid) if not isinstance(tid, ObjectId) else tid
            for tid in task_ids if tid
        ]
        
        objetivo_oid = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        
        # Actualizar en local
        result = local_col.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": {"objetivo_id": objetivo_oid}}
        )
        
        # Sincronizar cada tarea actualizada con la nube
        if remote_col is not None:
            try:
                remote_col.update_many(
                    {"_id": {"$in": object_ids}},
                    {"$set": {"objetivo_id": objetivo_oid}}
                )
                print(f"🎯 {result.modified_count} tareas asignadas al objetivo {goal_id} y sincronizadas.")
            except Exception as e:
                print(f"⚠️ Error al sincronizar asignación de objetivo: {e}")
        else:
            print(f"🎯 {result.modified_count} tareas asignadas al objetivo {goal_id} (solo local).")
        
        return result.modified_count
