from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_collection, sync_from_remote, sync_to_remote, get_app_user_id


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


class Upload_model:
    """Gestion de la coleccion 'Uploads'."""

    COLLECTION = "Uploads"
    DEFAULT_USER_ID = get_app_user_id()

    @staticmethod
    def get_all_uploads(usuario_id=None):
        local_col, _ = get_collection(Upload_model.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("uploaded_at", -1))

    @staticmethod
    def get_upload_by_id(upload_id, usuario_id=None):
        local_col, _ = get_collection(Upload_model.COLLECTION)
        _id = ObjectId(upload_id) if not isinstance(upload_id, ObjectId) else upload_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        doc = local_col.find_one(query)
        if not doc:
            sync_from_remote(Upload_model.COLLECTION, {"_id": _id})
            doc = local_col.find_one(query)
        return doc

    @staticmethod
    def insert_upload(doc_data, usuario_id=None):
        local_col, _ = get_collection(Upload_model.COLLECTION)

        uid = usuario_id or get_app_user_id()
        doc_data["usuario_id"] = doc_data.get("usuario_id") or uid

        if "uploaded_at" not in doc_data:
            doc_data["uploaded_at"] = datetime.utcnow()

        if doc_data.get("usuario_id") and not isinstance(doc_data["usuario_id"], ObjectId):
            try:
                doc_data["usuario_id"] = ObjectId(str(doc_data["usuario_id"]))
            except Exception:
                doc_data["usuario_id"] = ObjectId(uid)

        result = local_col.insert_one(doc_data)
        doc_data["_id"] = result.inserted_id

        sync_to_remote(Upload_model.COLLECTION, doc_data)
        print(f"Archivo insertado y sincronizado: {doc_data['_id']}")
        return doc_data

    @staticmethod
    def delete_upload(upload_id, usuario_id=None):
        local_col, remote_col = get_collection(Upload_model.COLLECTION)
        _id = ObjectId(upload_id) if not isinstance(upload_id, ObjectId) else upload_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        res = local_col.delete_one(query)

        if remote_col is not None:
            try:
                remote_col.delete_one(query)
            except Exception:
                pass

        return res.deleted_count > 0



