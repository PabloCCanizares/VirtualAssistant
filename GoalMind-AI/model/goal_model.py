from database.mongo_conn import get_collection, sync_to_remote, get_app_user_id
from bson import ObjectId
from datetime import datetime


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


class GoalModel:
    """Gestión de la colección 'Goals'."""
    COLLECTION = "Goals"

    @staticmethod
    def get_by_user_id(user_id):
        """
        Devuelve la lista de goals para un usuario dado.
        - user_id: str | ObjectId
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        cursor = local_col.find(_uid_filter(user_id)).sort("fecha_inicio", -1)
        return list(cursor)
    

    # -------------------------------------------------------------
    #  OBTENER TODAS
    # -------------------------------------------------------------
    @staticmethod
    def get_all_goals(usuario_id=None):
        """
        Devuelve todos los objetivos del usuario actual.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("created_at", -1))

    # -------------------------------------------------------------
    #  OBTENER UNA POR ID
    # -------------------------------------------------------------
    @staticmethod
    def get_goal_by_id(goal_id, usuario_id=None):
        """
        Devuelve un objetivo por su _id.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        _id = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        return local_col.find_one({"_id": _id, **_uid_filter(usuario_id)})

    @staticmethod
    def get_by_project(project_id, usuario_id=None):
        """
        Devuelve todos los objetivos asociados a un proyecto.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
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
        return list(local_col.find(base_query).sort("created_at", -1))
    
    @staticmethod
    def insert_goal(goal_data, usuario_id=None):
        """
        Inserta un objetivo en la base local y lo sincroniza con la remota si está disponible.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)

        uid = usuario_id or get_app_user_id()
        goal_data["usuario_id"] = goal_data.get("usuario_id") or uid

        if "created_at" not in goal_data:
            goal_data["created_at"] = datetime.utcnow()

        if "event_ids" not in goal_data:
            goal_data["event_ids"] = []

        if goal_data.get("project_id") and not isinstance(goal_data["project_id"], ObjectId):
            goal_data["project_id"] = ObjectId(str(goal_data["project_id"]))

        if goal_data.get("usuario_id") and not isinstance(goal_data["usuario_id"], ObjectId):
            try:
                goal_data["usuario_id"] = ObjectId(str(goal_data["usuario_id"]))
            except Exception:
                pass

        result = local_col.insert_one(goal_data)
        goal_data["_id"] = result.inserted_id

        sync_to_remote(GoalModel.COLLECTION, goal_data)

        print(f" Objetivo insertado localmente y sincronizado: {goal_data['_id']}")
        return goal_data
    
    
    @staticmethod
    def update_goal(goal_id, updates: dict, usuario_id=None):
        """
        Actualiza un objetivo localmente y sincroniza los cambios con la base remota.
        Solo actualiza si el usuario es propietario del objetivo.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        _id = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id

        norm = dict(updates) if updates else {}

        def _parse_date(v):
            if not v:
                return None
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "").strip())
            except Exception:
                return None

        if "fecha_inicio" in norm:
            norm["fecha_inicio"] = _parse_date(norm["fecha_inicio"])
        if "fecha_fin" in norm:
            norm["fecha_fin"] = _parse_date(norm["fecha_fin"])

        if "usuario_id" in norm and norm["usuario_id"]:
            try:
                norm["usuario_id"] = ObjectId(str(norm["usuario_id"]))
            except Exception:
                norm["usuario_id"] = None

        if "project_id" in norm and norm["project_id"]:
            try:
                norm["project_id"] = ObjectId(str(norm["project_id"]))
            except Exception:
                norm["project_id"] = None

        if "progreso" in norm and norm["progreso"] is not None:
            try:
                norm["progreso"] = int(norm["progreso"])
            except Exception:
                pass

        norm["updated_at"] = datetime.utcnow()

        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": norm})

        updated_goal = local_col.find_one({"_id": _id})

        sync_to_remote(GoalModel.COLLECTION, updated_goal)

        print(f"♻️ Objetivo {_id} actualizado y sincronizado.")
        return updated_goal
    

    @staticmethod
    def find_by_category(category_id, usuario_id=None):
        """
        Devuelve todos los objetivos que contengan una categoría específica.
        
        Args:
            category_id: ObjectId o string del ID de la categoría
            usuario_id: ID del usuario para filtrar
            
        Returns:
            list: Lista de objetivos que pertenecen a la categoría especificada
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        query = {"categorias": _id, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("created_at", -1))
    
    @staticmethod
    def search_by_categories(category_ids: list, usuario_id=None):
        """
        Busca objetivos que contengan al menos una de las categorías especificadas.
        
        Args:
            category_ids (list): Lista de IDs de categorías
            usuario_id: ID del usuario para filtrar
            
        Returns:
            list: Lista de objetivos que coinciden con los criterios
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        
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

    @staticmethod
    def search_by_name(nombre: str, limit: int = 10, usuario_id=None):
        """
        Busca objetivos cuyo título contenga el texto dado (case-insensitive).
        Devuelve hasta 'limit' resultados.
        """
        local_col, _ = get_collection(GoalModel.COLLECTION)
        if not nombre or not nombre.strip():
            return []
        
        import re
        regex = re.compile(re.escape(nombre.strip()), re.IGNORECASE)
        query = {"titulo": {"$regex": regex}, **_uid_filter(usuario_id)}
        cursor = local_col.find(query).sort("created_at", -1).limit(limit)
        return list(cursor)

    # -------------------------------------------------------------
    #  EVENT_IDS: Añadir / Eliminar evento asociado
    # -------------------------------------------------------------
    @staticmethod
    def add_event_to_goal(goal_id, event_id, usuario_id=None):
        """
        Añade un event_id al array event_ids del objetivo.
        Usa $addToSet para evitar duplicados.
        Solo modifica si el usuario es propietario del objetivo.
        """
        local_col, remote_col = get_collection(GoalModel.COLLECTION)
        _gid = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        _eid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id

        query = {"_id": _gid, **_uid_filter(usuario_id)}
        local_col.update_one(
            query,
            {"$addToSet": {"event_ids": _eid}},
            upsert=False
        )

        if remote_col is not None:
            try:
                remote_col.update_one(
                    query,
                    {"$addToSet": {"event_ids": _eid}},
                    upsert=False
                )
            except Exception as e:
                print(f"⚠️ Error al sincronizar add_event_to_goal en remoto: {e}")

        print(f"📅 Evento {_eid} asociado a objetivo {_gid}.")

    @staticmethod
    def remove_event_from_goal(goal_id, event_id, usuario_id=None):
        """
        Elimina un event_id del array event_ids del objetivo.
        Usa $pull para eliminarlo del array.
        Solo modifica si el usuario es propietario del objetivo.
        """
        local_col, remote_col = get_collection(GoalModel.COLLECTION)
        _gid = ObjectId(goal_id) if not isinstance(goal_id, ObjectId) else goal_id
        _eid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id

        query = {"_id": _gid, **_uid_filter(usuario_id)}
        local_col.update_one(
            query,
            {"$pull": {"event_ids": _eid}}
        )

        if remote_col is not None:
            try:
                remote_col.update_one(
                    query,
                    {"$pull": {"event_ids": _eid}}
                )
            except Exception as e:
                print(f"⚠️ Error al sincronizar remove_event_from_goal en remoto: {e}")

        print(f"🗑️ Evento {_eid} desasociado de objetivo {_gid}.")

    @staticmethod
    def delete_goal(goal_id, usuario_id=None):
        """
        Elimina un objetivo tanto en la base local como remota (si está disponible).
        Solo elimina si el usuario es propietario del objetivo.
        Devuelve True si se eliminó, False si no se encontró.
        """
        local_col, remote_col = get_collection(GoalModel.COLLECTION)
        queries = []
        if isinstance(goal_id, ObjectId):
            queries.append({"_id": goal_id})
        else:
            try:
                if ObjectId.is_valid(str(goal_id)):
                    queries.append({"_id": ObjectId(str(goal_id))})
            except Exception:
                pass
        if goal_id is not None:
            queries.append({"_id": str(goal_id)})

        if not queries:
            return False

        uid_filter = _uid_filter(usuario_id)
        deleted_local = 0
        for query in queries:
            merged_query = {**query, **uid_filter}
            res = local_col.delete_one(merged_query)
            deleted_local += res.deleted_count

        deleted_remote = 0
        if remote_col is not None:
            for query in queries:
                try:
                    merged_query = {**query, **uid_filter}
                    res = remote_col.delete_one(merged_query)
                    deleted_remote += res.deleted_count
                except Exception:
                    pass
            print("🗑️ Objetivo eliminado en local y remoto.")
        else:
            print("⚠️ Objetivo eliminado solo localmente (sin conexión remota).")

        return (deleted_local + deleted_remote) > 0

    @staticmethod
    def delete_goals_by_ids(ids, usuario_id=None):
        """
        Elimina varios objetivos por sus _id. Devuelve el nº de documentos eliminados.
        Solo elimina objetivos del usuario actual.
        """
        local_col, remote_col = get_collection(GoalModel.COLLECTION)
        object_ids = []
        string_ids = []
        for s in ids:
            if not s:
                continue
            try:
                if isinstance(s, ObjectId):
                    object_ids.append(s)
                elif ObjectId.is_valid(str(s)):
                    object_ids.append(ObjectId(str(s)))
                else:
                    string_ids.append(str(s))
            except Exception:
                string_ids.append(str(s))

        if not object_ids and not string_ids:
            return 0

        query = {"$or": []}
        if object_ids:
            query["$or"].append({"_id": {"$in": object_ids}})
        if string_ids:
            query["$or"].append({"_id": {"$in": string_ids}})

        uid_filter = _uid_filter(usuario_id)
        merged_query = {**query, **uid_filter}

        res = local_col.delete_many(merged_query)

        if remote_col is not None:
            try:
                remote_col.delete_many(merged_query)
            except Exception:
                pass

        return res.deleted_count
