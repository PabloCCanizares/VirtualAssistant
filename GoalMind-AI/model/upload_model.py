from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_collection, sync_from_remote, sync_to_remote


class Upload_model:
    """Gestion de la coleccion 'Uploads'."""

    COLLECTION = "Uploads"
    DEFAULT_USER_ID = "66ffbbbbbbbbbbbbbbbb0100"

    @staticmethod
    def get_all_uploads(user_id=None):
        local_col, _ = get_collection(Upload_model.COLLECTION)
        uid = user_id or Upload_model.DEFAULT_USER_ID
        try:
            uid = ObjectId(uid) if not isinstance(uid, ObjectId) else uid
        except Exception:
            uid = Upload_model.DEFAULT_USER_ID
            uid = ObjectId(uid)
        return list(local_col.find({"id_usuario": uid}).sort("uploaded_at", -1))

    @staticmethod
    def get_upload_by_id(upload_id):
        local_col, _ = get_collection(Upload_model.COLLECTION)
        _id = ObjectId(upload_id) if not isinstance(upload_id, ObjectId) else upload_id

        doc = local_col.find_one({"_id": _id})
        if not doc:
            sync_from_remote(Upload_model.COLLECTION, {"_id": _id})
            doc = local_col.find_one({"_id": _id})
        return doc

    @staticmethod
    def insert_upload(doc_data):
        local_col, _ = get_collection(Upload_model.COLLECTION)

        if "uploaded_at" not in doc_data:
            doc_data["uploaded_at"] = datetime.utcnow()
        if "id_usuario" not in doc_data or not doc_data.get("id_usuario"):
            doc_data["id_usuario"] = Upload_model.DEFAULT_USER_ID
        if doc_data.get("id_usuario") and not isinstance(doc_data["id_usuario"], ObjectId):
            try:
                doc_data["id_usuario"] = ObjectId(str(doc_data["id_usuario"]))
            except Exception:
                doc_data["id_usuario"] = ObjectId(Upload_model.DEFAULT_USER_ID)

        result = local_col.insert_one(doc_data)
        doc_data["_id"] = result.inserted_id

        sync_to_remote(Upload_model.COLLECTION, doc_data)
        print(f"Archivo insertado y sincronizado: {doc_data['_id']}")
        return doc_data

    @staticmethod
    def delete_upload(upload_id):
        local_col, remote_col = get_collection(Upload_model.COLLECTION)
        _id = ObjectId(upload_id) if not isinstance(upload_id, ObjectId) else upload_id

        res = local_col.delete_one({"_id": _id})

        if remote_col is not None:
            try:
                remote_col.delete_one({"_id": _id})
            except Exception:
                pass

        return res.deleted_count > 0



