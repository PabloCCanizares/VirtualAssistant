from datetime import datetime

from bson import ObjectId

from database.mongo_conn import get_collection, sync_from_remote, sync_to_remote


class ProjectModel:
    """Gestión de la colección 'Projects'."""

    COLLECTION = "Projects"

    @staticmethod
    def get_all_projects():
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        return list(local_col.find().sort("created_at", -1))

    @staticmethod
    def get_project_by_id(project_id):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id

        project = local_col.find_one({"_id": _id})
        if not project:
            sync_from_remote(ProjectModel.COLLECTION, {"_id": _id})
            project = local_col.find_one({"_id": _id})
        return project

    @staticmethod
    def insert_project(project_data):
        local_col, _ = get_collection(ProjectModel.COLLECTION)

        if "created_at" not in project_data:
            project_data["created_at"] = datetime.utcnow()

        if project_data.get("id_usuario"):
            try:
                project_data["id_usuario"] = ObjectId(str(project_data["id_usuario"]))
            except Exception:
                pass

        result = local_col.insert_one(project_data)
        project_data["_id"] = result.inserted_id

        sync_to_remote(ProjectModel.COLLECTION, project_data)
        print(f"📁 Proyecto insertado localmente y sincronizado: {project_data['_id']}")
        return project_data

    @staticmethod
    def update_project(project_id, updates):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id

        norm = dict(updates) if updates else {}

        if "id_usuario" in norm and norm["id_usuario"]:
            try:
                norm["id_usuario"] = ObjectId(str(norm["id_usuario"]))
            except Exception:
                pass

        def _parse_date(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            try:
                return datetime.fromisoformat(str(value).replace("Z", "").strip())
            except Exception:
                return None

        if "fecha_inicio" in norm:
            norm["fecha_inicio"] = _parse_date(norm["fecha_inicio"])
        if "fecha_fin" in norm:
            norm["fecha_fin"] = _parse_date(norm["fecha_fin"])

        norm["updated_at"] = datetime.utcnow()

        local_col.update_one({"_id": _id}, {"$set": norm})
        updated_project = local_col.find_one({"_id": _id})

        sync_to_remote(ProjectModel.COLLECTION, updated_project)
        print(f"♻️ Proyecto {_id} actualizado y sincronizado.")
        return updated_project

    @staticmethod
    def delete_project(project_id):
        local_col, remote_col = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id

        res = local_col.delete_one({"_id": _id})

        if remote_col:
            try:
                remote_col.delete_one({"_id": _id})
            except Exception:
                pass

        return res.deleted_count > 0
