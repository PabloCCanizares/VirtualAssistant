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


class ProjectModel:
    """Gestión de la colección 'Projects'."""

    COLLECTION = "Projects"

    @staticmethod
    def get_all_projects(usuario_id=None):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("created_at", -1))

    @staticmethod
    def get_by_user_id(user_id):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        return list(local_col.find(_uid_filter(user_id)).sort("created_at", -1))

    @staticmethod
    def get_project_by_id(project_id, usuario_id=None):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id

        query = {"_id": _id, **_uid_filter(usuario_id)}
        project = local_col.find_one(query)
        if not project:
            sync_from_remote(ProjectModel.COLLECTION, {"_id": _id})
            project = local_col.find_one(query)
        return project

    @staticmethod
    def insert_project(project_data, usuario_id=None):
        local_col, _ = get_collection(ProjectModel.COLLECTION)

        uid = usuario_id or get_app_user_id()
        project_data["usuario_id"] = project_data.get("usuario_id") or uid

        if "created_at" not in project_data:
            project_data["created_at"] = datetime.utcnow()

        if project_data.get("usuario_id"):
            try:
                project_data["usuario_id"] = ObjectId(str(project_data["usuario_id"]))
            except Exception:
                pass

        result = local_col.insert_one(project_data)
        project_data["_id"] = result.inserted_id

        sync_to_remote(ProjectModel.COLLECTION, project_data)
        print(f"Proyecto insertado localmente y sincronizado: {project_data['_id']}")
        return project_data

    @staticmethod
    def update_project(project_id, updates, usuario_id=None):
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(project_id) if not isinstance(project_id, ObjectId) else project_id

        norm = dict(updates) if updates else {}

        if "usuario_id" in norm and norm["usuario_id"]:
            try:
                norm["usuario_id"] = ObjectId(str(norm["usuario_id"]))
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

        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": norm})
        updated_project = local_col.find_one({"_id": _id})

        sync_to_remote(ProjectModel.COLLECTION, updated_project)
        print(f"Proyecto {_id} actualizado y sincronizado.")
        return updated_project

    @staticmethod
    def delete_project(project_id, usuario_id=None):
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

        uid_filter = _uid_filter(usuario_id)
        delete_queries = []
        for q in queries:
            merged = {**q, **uid_filter}
            delete_queries.append(merged)

        delete_query = {"$or": delete_queries}
        deleted_local = local_col.delete_many(delete_query).deleted_count

        deleted_remote = 0
        if remote_col is not None:
            try:
                deleted_remote = remote_col.delete_many(delete_query).deleted_count
            except Exception:
                pass

        return (deleted_local + deleted_remote) > 0

    @staticmethod
    def calculate_progress_from_goals(goals: list) -> float:
        """
        Calcula el progreso medio de un proyecto a partir de una lista de
        objetivos ya cargada, haciendo la media de su campo 'progreso'.

        Returns:
            float: Media de progreso (0.0–100.0), o 0.0 si la lista está vacía.
        """
        if not goals:
            return 0.0
        progresos = []
        for g in goals:
            raw = g.get("progreso")
            try:
                progresos.append(float(raw or 0.0))
            except Exception:
                progresos.append(0.0)
        return round(sum(progresos) / len(progresos), 2)

    @staticmethod
    def calculate_progress(project_id, usuario_id=None) -> float:
        """
        Calcula el progreso medio de un proyecto como la media del campo
        'progreso' de todos sus objetivos asociados.

        Returns:
            float: Media de progreso (0.0–100.0), o 0.0 si no hay objetivos.
        """
        from model.goal_model import GoalModel

        goals = GoalModel.get_by_project(project_id, usuario_id=usuario_id)
        return ProjectModel.calculate_progress_from_goals(goals)

    @staticmethod
    def find_by_category(category_id, usuario_id=None):
        """
        Devuelve todos los proyectos que contengan una categoría específica.
        
        Args:
            category_id: ObjectId o string del ID de la categoría
            usuario_id: ID del usuario para filtrar
            
        Returns:
            list: Lista de proyectos que pertenecen a la categoría especificada
        """
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        query = {"categorias": _id, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("created_at", -1))
    
    @staticmethod
    def search_by_categories(category_ids: list, usuario_id=None):
        """
        Busca proyectos que contengan al menos una de las categorías especificadas.
        
        Args:
            category_ids (list): Lista de IDs de categorías
            usuario_id: ID del usuario para filtrar
            
        Returns:
            list: Lista de proyectos que coinciden con los criterios
        """
        local_col, _ = get_collection(ProjectModel.COLLECTION)
        
        if not category_ids:
            return list(local_col.find(_uid_filter(usuario_id)).sort("created_at", -1))
        
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
            return list(local_col.find(_uid_filter(usuario_id)).sort("created_at", -1))
        
        query = {"categorias": {"$in": cat_oids}, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("created_at", -1))
