from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_app_user_id, get_collection, sync_from_remote, sync_to_remote


def _uid_filter(usuario_id):
    uid = usuario_id or get_app_user_id()
    conditions = [{"usuario_id": uid}]
    try:
        if ObjectId.is_valid(str(uid)):
            conditions.append({"usuario_id": ObjectId(str(uid))})
    except Exception:
        pass
    return {"$or": conditions} if len(conditions) > 1 else conditions[0]


class ProjectDocumentFolderModel:
    """Gestion de carpetas logicas para documentos de proyecto."""

    COLLECTION = "ProjectDocumentFolders"

    @staticmethod
    def get_by_project(project_id, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentFolderModel.COLLECTION)
        queries = []
        if isinstance(project_id, ObjectId):
            queries.append({"project_id": project_id})
        else:
            try:
                if ObjectId.is_valid(str(project_id)):
                    queries.append({"project_id": ObjectId(str(project_id))})
            except Exception:
                pass
            if project_id is not None:
                queries.append({"project_id": str(project_id)})

        if not queries:
            return []

        query = {"$and": [{"$or": queries}, _uid_filter(usuario_id)]}
        return list(local_col.find(query).sort("created_at", 1))

    @staticmethod
    def get_folder_by_id(folder_id, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentFolderModel.COLLECTION)
        _id = ObjectId(folder_id) if not isinstance(folder_id, ObjectId) else folder_id
        query = {"_id": _id, **_uid_filter(usuario_id)}
        folder = local_col.find_one(query)
        if not folder:
            sync_from_remote(ProjectDocumentFolderModel.COLLECTION, {"_id": _id})
            folder = local_col.find_one(query)
        return folder

    @staticmethod
    def insert_folder(folder_data, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentFolderModel.COLLECTION)
        data = dict(folder_data or {})

        uid = usuario_id or get_app_user_id()
        data["usuario_id"] = data.get("usuario_id") or uid
        data["name"] = (data.get("name") or "").strip()
        if "created_at" not in data:
            data["created_at"] = datetime.utcnow()
        if data.get("project_id") and not isinstance(data["project_id"], ObjectId):
            data["project_id"] = ObjectId(str(data["project_id"]))

        result = local_col.insert_one(data)
        data["_id"] = result.inserted_id
        sync_to_remote(ProjectDocumentFolderModel.COLLECTION, data)
        return data

    @staticmethod
    def delete_folder(folder_id, usuario_id=None):
        local_col, remote_col = get_collection(ProjectDocumentFolderModel.COLLECTION)
        _id = ObjectId(folder_id) if not isinstance(folder_id, ObjectId) else folder_id
        query = {"_id": _id, **_uid_filter(usuario_id)}
        result = local_col.delete_one(query)

        if remote_col is not None:
            try:
                remote_col.delete_one(query)
            except Exception:
                pass

        return result.deleted_count > 0
