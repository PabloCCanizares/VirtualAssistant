from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_collection, sync_from_remote, sync_to_remote, get_app_user_id
from database.gridfs_storage import (
    delete_file_from_local_storage,
    delete_file_from_remote_storage,
    promote_local_file_to_remote,
)


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


class ProjectDocumentModel:
    """Gestión de la colección 'ProjectDocuments'."""

    COLLECTION = "ProjectDocuments"

    @staticmethod
    def get_all_documents(usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("uploaded_at", -1))

    @staticmethod
    def get_by_project(project_id, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
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

        uid_filter = _uid_filter(usuario_id)
        base_query = {"$and": [{"$or": queries}, uid_filter]}
        return list(local_col.find(base_query).sort("uploaded_at", -1))

    @staticmethod
    def get_document_by_id(doc_id, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        _id = ObjectId(doc_id) if not isinstance(doc_id, ObjectId) else doc_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        doc = local_col.find_one(query)
        if not doc:
            sync_from_remote(ProjectDocumentModel.COLLECTION, {"_id": _id})
            doc = local_col.find_one(query)
        return doc

    @staticmethod
    def insert_document(doc_data, usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)

        uid = usuario_id or get_app_user_id()
        doc_data["usuario_id"] = doc_data.get("usuario_id") or uid

        if "uploaded_at" not in doc_data:
            doc_data["uploaded_at"] = datetime.utcnow()

        if doc_data.get("project_id") and not isinstance(doc_data["project_id"], ObjectId):
            doc_data["project_id"] = ObjectId(str(doc_data["project_id"]))
        if doc_data.get("goal_id") and not isinstance(doc_data["goal_id"], ObjectId):
            doc_data["goal_id"] = ObjectId(str(doc_data["goal_id"]))
        if doc_data.get("upload_id") and not isinstance(doc_data["upload_id"], ObjectId):
            doc_data["upload_id"] = ObjectId(str(doc_data["upload_id"]))

        result = local_col.insert_one(doc_data)
        doc_data["_id"] = result.inserted_id

        if not doc_data.get("remote_sync_pending"):
            sync_to_remote(ProjectDocumentModel.COLLECTION, doc_data)
        print(f"Documento insertado y sincronizado: {doc_data['_id']}")
        return doc_data

    @staticmethod
    def update_document(doc_id, updates, usuario_id=None, sync_remote=True):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        _id = ObjectId(doc_id) if not isinstance(doc_id, ObjectId) else doc_id
        norm = dict(updates or {})
        for key in ("project_id", "goal_id", "upload_id", "local_upload_id"):
            if norm.get(key) and not isinstance(norm[key], ObjectId):
                try:
                    norm[key] = ObjectId(str(norm[key]))
                except Exception:
                    pass
        norm["updated_at"] = datetime.utcnow()
        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": norm})
        updated = local_col.find_one({"_id": _id})
        if sync_remote and updated and not updated.get("remote_sync_pending"):
            sync_to_remote(ProjectDocumentModel.COLLECTION, updated)
        return updated

    @staticmethod
    def get_pending_remote_uploads(usuario_id=None):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        query = {
            "$and": [
                {"remote_sync_pending": True},
                {"local_upload_id": {"$exists": True, "$ne": None}},
                _uid_filter(usuario_id),
            ]
        }
        return list(local_col.find(query).sort("uploaded_at", 1))

    @staticmethod
    def promote_pending_remote_uploads(usuario_id=None, app=None):
        promoted = 0
        for doc in ProjectDocumentModel.get_pending_remote_uploads(usuario_id=usuario_id):
            remote_id = promote_local_file_to_remote(
                doc.get("local_upload_id"),
                original_name=doc.get("original_name") or doc.get("filename") or "documento",
                content_type=doc.get("content_type"),
                metadata={
                    "project_id": str(doc.get("project_id", "")),
                    "goal_id": str(doc.get("goal_id", "")) if doc.get("goal_id") else "",
                    "usuario_id": str(doc.get("usuario_id", "")),
                },
                app=app,
            )
            if not remote_id:
                continue
            ProjectDocumentModel.update_document(
                doc["_id"],
                {"upload_id": remote_id, "remote_sync_pending": False},
                usuario_id=usuario_id,
                sync_remote=True,
            )
            promoted += 1
        return promoted

    @staticmethod
    def delete_document(doc_id, usuario_id=None):
        local_col, remote_col = get_collection(ProjectDocumentModel.COLLECTION)
        _id = ObjectId(doc_id) if not isinstance(doc_id, ObjectId) else doc_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        doc = local_col.find_one(query)
        if not doc:
            return False
        if doc.get("local_upload_id"):
            try:
                delete_file_from_local_storage(doc.get("local_upload_id"))
            except Exception:
                pass
        if doc.get("upload_id"):
            try:
                delete_file_from_remote_storage(doc.get("upload_id"))
            except Exception:
                pass
        res = local_col.delete_one(query)

        if remote_col is not None:
            try:
                remote_col.delete_one(query)
            except Exception:
                pass

        return res.deleted_count > 0
