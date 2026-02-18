from bson import ObjectId
from database.mongo_conn import get_collection, get_app_user_id


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


class eventModel:
    COLLECTION = "Events"

    @staticmethod
    def get_all_events(usuario_id=None):
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_task(task_id, usuario_id=None):
        """Obtiene todos los eventos asociados a una tarea específica."""
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(task_id) if not isinstance(task_id, ObjectId) else task_id
        except Exception:
            return []
        query = {"id_tarea": oid, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_goal(goal_id, usuario_id=None):
        """Obtiene todos los eventos asociados a un objetivo específico."""
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        except Exception:
            return []
        query = {"id_objetivo": oid, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def get_event_by_id(event_id, usuario_id=None):
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        except Exception:
            return None
        return local_col.find_one({"_id": oid, **_uid_filter(usuario_id)})

    @staticmethod
    def get_events_by_user(user_id):
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find(_uid_filter(user_id)).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_type(type_norm, usuario_id=None):
        """type_norm debe venir ya normalizado (sin tildes, minúsculas)"""
        local_col, _ = get_collection(eventModel.COLLECTION)
        query = {"tipo_evento": type_norm, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def insert_event(data: dict, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        
        uid = usuario_id or get_app_user_id()
        data["usuario_id"] = data.get("usuario_id") or uid
        
        res = local_col.insert_one(data)
        if cloud_col is not None:
            try:
                cloud_col.insert_one({**data, "_id": res.inserted_id})
            except Exception:
                pass
        return res.inserted_id

    @staticmethod
    def update_event(event_id: str, updates: dict, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        query = {"_id": oid, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": updates})
        if cloud_col is not None:
            try:
                cloud_col.update_one(query, {"$set": updates})
            except Exception:
                pass

    @staticmethod
    def delete_event(event_id: str, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        query = {"_id": oid, **_uid_filter(usuario_id)}
        local_col.delete_one(query)
        if cloud_col is not None:
            try:
                cloud_col.delete_one(query)
            except Exception:
                pass

    @staticmethod
    def delete_events_by_ids(ids: list[str], usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oids = []
        for s in ids:
            try:
                oids.append(ObjectId(s))
            except Exception:
                continue
        if not oids:
            return 0
        query = {"_id": {"$in": oids}, **_uid_filter(usuario_id)}
        res = local_col.delete_many(query)
        if cloud_col is not None:
            try:
                cloud_col.delete_many(query)
            except Exception:
                pass
        return res.deleted_count
