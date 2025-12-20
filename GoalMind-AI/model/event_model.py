from bson import ObjectId
from database.mongo_conn import get_collection  

class eventModel:
    COLLECTION = "Events"

    @staticmethod
    def get_all_events():
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find().sort("fecha_inicio", 1))

    @staticmethod
    def get_event_by_id(event_id):
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        except Exception:
            return None
        return local_col.find_one({"_id": oid})

    @staticmethod
    def get_events_by_user(user_id):
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        except Exception:
            return []
        return list(local_col.find({"id_usuario": oid}).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_type(type_norm):
        """type_norm debe venir ya normalizado (sin tildes, minúsculas)"""
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find({"tipo_evento": type_norm}).sort("fecha_inicio", 1))

    @staticmethod
    def insert_event(data: dict):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        res = local_col.insert_one(data)
        # si usas sync opcional a la nube, réplicalo como haces en TaskModel
        if cloud_col:
            try:
                cloud_col.insert_one({**data, "_id": res.inserted_id})
            except Exception:
                pass
        return res.inserted_id

    @staticmethod
    def update_event(event_id: str, updates: dict):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        local_col.update_one({"_id": oid}, {"$set": updates})
        if cloud_col:
            try:
                cloud_col.update_one({"_id": oid}, {"$set": updates})
            except Exception:
                pass

    @staticmethod
    def delete_event(event_id: str):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        local_col.delete_one({"_id": oid})
        if cloud_col:
            try:
                cloud_col.delete_one({"_id": oid})
            except Exception:
                pass

    @staticmethod
    def delete_events_by_ids(ids: list[str]):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oids = []
        for s in ids:
            try:
                oids.append(ObjectId(s))
            except Exception:
                continue
        if not oids:
            return 0
        res = local_col.delete_many({"_id": {"$in": oids}})
        if cloud_col:
            try:
                cloud_col.delete_many({"_id": {"$in": oids}})
            except Exception:
                pass
        return res.deleted_count
