from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_collection, sync_from_remote, sync_to_remote


class ProjectDocumentModel:
    """Gestión de la colección 'ProjectDocuments'."""

    COLLECTION = "ProjectDocuments"

    @staticmethod
    def get_all_documents():
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        return list(local_col.find().sort("uploaded_at", -1))

    @staticmethod
    def get_by_project(project_id):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        pid = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id
        return list(local_col.find({"project_id": pid}).sort("uploaded_at", -1))

    @staticmethod
    def get_document_by_id(doc_id):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)
        _id = ObjectId(doc_id) if not isinstance(doc_id, ObjectId) else doc_id

        doc = local_col.find_one({"_id": _id})
        if not doc:
            sync_from_remote(ProjectDocumentModel.COLLECTION, {"_id": _id})
            doc = local_col.find_one({"_id": _id})
        return doc

    @staticmethod
    def insert_document(doc_data):
        local_col, _ = get_collection(ProjectDocumentModel.COLLECTION)

        if "uploaded_at" not in doc_data:
            doc_data["uploaded_at"] = datetime.utcnow()

        if doc_data.get("project_id") and not isinstance(doc_data["project_id"], ObjectId):
            doc_data["project_id"] = ObjectId(str(doc_data["project_id"]))
        if doc_data.get("goal_id") and not isinstance(doc_data["goal_id"], ObjectId):
            doc_data["goal_id"] = ObjectId(str(doc_data["goal_id"]))

        result = local_col.insert_one(doc_data)
        doc_data["_id"] = result.inserted_id

        sync_to_remote(ProjectDocumentModel.COLLECTION, doc_data)
        print(f"📄 Documento insertado y sincronizado: {doc_data['_id']}")
        return doc_data

    @staticmethod
    def delete_document(doc_id):
        local_col, remote_col = get_collection(ProjectDocumentModel.COLLECTION)
        _id = ObjectId(doc_id) if not isinstance(doc_id, ObjectId) else doc_id

        res = local_col.delete_one({"_id": _id})

        if remote_col:
            try:
                remote_col.delete_one({"_id": _id})
            except Exception:
                pass

        return res.deleted_count > 0
