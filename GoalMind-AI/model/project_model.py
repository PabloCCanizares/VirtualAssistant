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
    def get_by_user_id(user_id):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        uid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        return list(local_col.find({"id_usuario": uid}).sort("created_at", -1))

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
        queries = []
        oid = None
        if isinstance(project_id, ObjectId):
            oid = project_id
        else:
            try:
                if ObjectId.is_valid(str(project_id)):
                    oid = ObjectId(str(project_id))
            except Exception:
                oid = None

        if oid is not None:
            queries.append({"_id": oid})
        if project_id is not None:
            queries.append({"_id": str(project_id)})

        if not queries:
            return False

        delete_query = {"$or": queries}
        deleted_local = local_col.delete_many(delete_query).deleted_count

        deleted_remote = 0
        if remote_col is not None:
            try:
                deleted_remote = remote_col.delete_many(delete_query).deleted_count
            except Exception:
                pass

        return (deleted_local + deleted_remote) > 0

    @staticmethod
    def find_by_category(category_id):
        """
        Devuelve todos los proyectos que contengan una categoría específica.
        
        Args:
            category_id: ObjectId o string del ID de la categoría
            
        Returns:
            list: Lista de proyectos que pertenecen a la categoría especificada
        """
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        # Buscar proyectos que contengan esta categoría en su array de categorías
        return list(local_col.find({"categorias": _id}).sort("created_at", -1))
    
    @staticmethod
    def search_by_categories(category_ids: list):
        """
        Busca proyectos que contengan al menos una de las categorías especificadas.
        
        Args:
            category_ids (list): Lista de IDs de categorías
            
        Returns:
            list: Lista de proyectos que coinciden con los criterios
        """
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        
        if not category_ids:
            return list(local_col.find().sort("created_at", -1))
        
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
        
        if not cat_oids:
            return list(local_col.find().sort("created_at", -1))
        
        return list(local_col.find({"categorias": {"$in": cat_oids}}).sort("created_at", -1))
