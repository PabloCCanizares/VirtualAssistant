from database.mongo_conn import get_collection, sync_to_remote, sync_from_remote, get_app_user_id
from bson import ObjectId
from datetime import datetime
from model.goal_model import GoalModel


def _uid_filter(usuario_id):
    """Construye filtro que matchea tanto string como ObjectId."""
    uid = usuario_id or get_app_user_id()
    conditions = [{"usuario_id": uid}]
    try:
        if ObjectId.is_valid(str(uid)):
            conditions.append({"usuario_id": ObjectId(str(uid))})
    except Exception:
        pass
    return {"$or": conditions} if len(conditions) > 1 else conditions[0]


class TaskModel:
    """Gestión de la colección 'tasks' con sincronización local/remota."""

    COLLECTION = "Tasks"

    @staticmethod
    def insert_task(task_data, usuario_id=None):
        """
        Inserta una tarea en la base local y la sincroniza con la remota si está disponible.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        
        uid = usuario_id or get_app_user_id()
        task_data["usuario_id"] = task_data.get("usuario_id") or uid

        # Asegurar que tenga fecha de creación
        if "fecha_creacion" not in task_data:
            task_data["fecha_creacion"] = datetime.utcnow()

        # Asegurar que tenga el array de eventos asociados
        if "event_ids" not in task_data:
            task_data["event_ids"] = []

        # Insertar en local
        result = local_col.insert_one(task_data)
        task_data["_id"] = result.inserted_id

        # Sincronizar con la nube
        sync_to_remote(TaskModel.COLLECTION, task_data)

        print(f"Tarea insertada localmente y sincronizada: {task_data['_id']}")
        return task_data
    
    @staticmethod
    def get_task_by_id(task_id, usuario_id=None):
        """
        Obtiene una tarea por su _id.
        Si no está en local, intenta descargarla desde la remota.
        Filtra por usuario_id.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        task = local_col.find_one(query)

        if not task:
            sync_from_remote(TaskModel.COLLECTION, {"_id": _id})
            task = local_col.find_one(query)

        return task

    @staticmethod
    def get_tasks_by_category(category_id, usuario_id=None):
        """
        Devuelve todas las tareas que contengan una categoría específica.
        
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        
        query = {"categorias": _id, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("fecha_creacion", -1))

    @staticmethod
    def search_tasks(nombre=None, categoria=None, category_ids=None, usuario_id=None):
        """
        Busca tareas por nombre (contenido) y/o categoría.
        La búsqueda por nombre es case-insensitive y parcial (regex).
        
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        
        query = {**_uid_filter(usuario_id)}
        
        # Filtro por nombre (búsqueda parcial case-insensitive)
        if nombre and nombre.strip():
            query["contenido"] = {"$regex": nombre.strip(), "$options": "i"}
        
        # Filtro por categorías (array de ObjectIds)
        if category_ids and len(category_ids) > 0:
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
                query["categorias"] = {"$in": cat_oids}
        
        return list(local_col.find(query).sort("fecha_creacion", -1))

    @staticmethod
    def get_all_tasks(usuario_id=None):
        """
        Devuelve todas las tareas del usuario actual.
        (No descarga desde remoto automáticamente.)
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)))

    @staticmethod
    def get_task_by_user(usuario_id):
        """
        Devuelve todas las tareas de un usuario específico.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)))

    @staticmethod
    def get_tasks_by_goal(goal_id, usuario_id=None):
        """
        Devuelve todas las tareas asociadas a un objetivo específico.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        queries = []
        if isinstance(goal_id, ObjectId):
            queries.append({"objetivo_id": goal_id})
            queries.append({"goal_id": goal_id})
        else:
            try:
                if ObjectId.is_valid(str(goal_id)):
                    oid = ObjectId(str(goal_id))
                    queries.append({"objetivo_id": oid})
                    queries.append({"goal_id": oid})
            except Exception:
                pass
            if goal_id is not None:
                queries.append({"objetivo_id": str(goal_id)})
                queries.append({"goal_id": str(goal_id)})

        if not queries:
            return []

        uid_filter = _uid_filter(usuario_id)
        base_query = {"$and": [{"$or": queries}, uid_filter]}
        return list(local_col.find(base_query).sort("fecha_creacion", -1))

    @staticmethod
    def delete_task(task_id, usuario_id=None):
        """
        Elimina una tarea tanto en la base local como remota (si está disponible).
        Solo elimina si el usuario es propietario de la tarea.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.delete_one(query)

        if remote_col is not None:
            try:
                remote_col.delete_one(query)
                print(f"Tarea eliminada en local y remoto: {_id}")
            except Exception:
                print(f"Tarea eliminada solo localmente: {_id}")
        else:
            print(f"Tarea eliminada solo localmente (sin conexión remota): {_id}")

    @staticmethod
    def delete_tasks_by_ids(task_ids, usuario_id=None):
        """
        Elimina varias tareas por sus _id. Devuelve el nº de documentos eliminados.
        Solo elimina tareas del usuario actual.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        ids = [
            ObjectId(tid) if not isinstance(tid, ObjectId) else tid
            for tid in task_ids if tid
        ]
        
        query = {"_id": {"$in": ids}, **_uid_filter(usuario_id)}
        res_local = local_col.delete_many(query)

        if remote_col is not None:
            try:
                remote_col.delete_many(query)
            except Exception:
                pass

        return res_local.deleted_count

    @staticmethod
    def update_task(task_id, updates, usuario_id=None):
        """
        Actualiza una tarea localmente y sincroniza los cambios con la base remota.
        Solo actualiza si el usuario es propietario de la tarea.
        """
        local_col, _ = get_collection(TaskModel.COLLECTION)
        _id = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": updates})

        updated_task = local_col.find_one({"_id": _id})

        sync_to_remote(TaskModel.COLLECTION, updated_task)

        print(f"Tarea {_id} actualizada y sincronizada.")

        if "estado" in updates and updated_task and updated_task.get("objetivo_id"):
            TaskModel.recalculate_goal_progress(updated_task["objetivo_id"], usuario_id=usuario_id)

        return updated_task

    @staticmethod
    def recalculate_goal_progress(goal_id, usuario_id=None):
        """
        Recalcula el progreso de un objetivo como la media de los porcentajes
        de sus tareas asociadas y lo guarda en el campo 'progreso' como decimal.
        """
        estado_pct = {"pendiente": 0.0, "en curso": 50.0, "completada": 100.0}

        tasks = TaskModel.get_tasks_by_goal(goal_id, usuario_id=usuario_id)
        if not tasks:
            progreso = 0.0
        else:
            total = sum(estado_pct.get(t.get("estado"), 0.0) for t in tasks)
            progreso = round(total / len(tasks), 2)

        local_col, _ = get_collection(GoalModel.COLLECTION)
        _id = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": {"progreso": progreso, "updated_at": datetime.utcnow()}})

        updated_goal = local_col.find_one({"_id": _id})
        sync_to_remote(GoalModel.COLLECTION, updated_goal)

        print(f"Progreso del objetivo {_id} recalculado: {progreso}%")
        return progreso

    @staticmethod
    def add_event_to_task(task_id, event_id, usuario_id=None):
        """
        Añade un event_id al array event_ids de la tarea.
        Usa $addToSet para evitar duplicados.
        Solo modifica si el usuario es propietario de la tarea.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        _tid = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id
        _eid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id

        query = {"_id": _tid, **_uid_filter(usuario_id)}
        local_col.update_one(
            query,
            {"$addToSet": {"event_ids": _eid}},
            upsert=False
        )

        if remote_col is not None:
            try:
                remote_col.update_one(
                    query,
                    {"$addToSet": {"event_ids": _eid}},
                    upsert=False
                )
            except Exception as e:
                print(f"Error al sincronizar add_event_to_task en remoto: {e}")

        print(f"Evento {_eid} asociado a tarea {_tid}.")

    @staticmethod
    def remove_event_from_task(task_id, event_id, usuario_id=None):
        """
        Elimina un event_id del array event_ids de la tarea.
        Usa $pull para eliminarlo del array.
        Solo modifica si el usuario es propietario de la tarea.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        _tid = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id
        _eid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id

        query = {"_id": _tid, **_uid_filter(usuario_id)}
        local_col.update_one(
            query,
            {"$pull": {"event_ids": _eid}}
        )

        if remote_col is not None:
            try:
                remote_col.update_one(
                    query,
                    {"$pull": {"event_ids": _eid}}
                )
            except Exception as e:
                print(f"Error al sincronizar remove_event_from_task en remoto: {e}")

        print(f"Evento {_eid} desasociado de tarea {_tid}.")

    @staticmethod
    def assign_goal_to_tasks(task_ids, goal_id, usuario_id=None):
        """
        Asigna un objetivo (goal_id) a múltiples tareas.
        Devuelve el número de tareas actualizadas.
        Solo modifica tareas del usuario actual.
        """
        local_col, remote_col = get_collection(TaskModel.COLLECTION)
        
        object_ids = [
            ObjectId(tid) if not isinstance(tid, ObjectId) else tid
            for tid in task_ids if tid
        ]
        
        objetivo_oid = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        
        query = {"_id": {"$in": object_ids}, **_uid_filter(usuario_id)}
        result = local_col.update_many(
            query,
            {"$set": {"objetivo_id": objetivo_oid}}
        )
        
        if remote_col is not None:
            try:
                remote_col.update_many(
                    query,
                    {"$set": {"objetivo_id": objetivo_oid}}
                )
                print(f" {result.modified_count} tareas asignadas al objetivo {goal_id} y sincronizadas.")
            except Exception as e:
                print(f" Error al sincronizar asignación de objetivo: {e}")
        else:
            print(f" {result.modified_count} tareas asignadas al objetivo {goal_id} (solo local).")
        
        return result.modified_count
