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


class CategoryModel:
    """Gestion de la coleccion 'Categories' con sincronizacion local/remota."""

    COLLECTION = "Categories"

    # -------------------------------------------------------------
    #  INSERTAR
    # -------------------------------------------------------------
    @staticmethod
    def insert_category(name: str, usuario_id=None):
        """
        Inserta una categoria en la base local y la sincroniza con la remota.
        Devuelve la categoria insertada con su _id.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        
        uid = usuario_id or get_app_user_id()

        existing = local_col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}, **_uid_filter(uid)})
        if existing:
            return None

        category_data = {
            "name": name.strip(),
            "usuario_id": uid,
            "created_at": datetime.utcnow()
        }

        result = local_col.insert_one(category_data)
        category_data["_id"] = result.inserted_id

        sync_to_remote(CategoryModel.COLLECTION, category_data)

        print(f"Categoria insertada: {category_data['_id']} - {name}")
        return category_data

    # -------------------------------------------------------------
    #  OBTENER TODAS
    # -------------------------------------------------------------
    @staticmethod
    def get_all_categories(usuario_id=None):
        """
        Devuelve todas las categorias del usuario actual ordenadas alfabeticamente por nombre.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("name", 1))

    # -------------------------------------------------------------
    #  OBTENER POR ID
    # -------------------------------------------------------------
    @staticmethod
    def get_category_by_id(category_id, usuario_id=None):
        """
        Obtiene una categoria por su _id.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        return local_col.find_one({"_id": _id, **_uid_filter(usuario_id)})

    # -------------------------------------------------------------
    #  OBTENER POR IDs (MULTIPLES)
    # -------------------------------------------------------------
    @staticmethod
    def get_categories_by_ids(category_ids: list, usuario_id=None):
        """
        Obtiene multiples categorias por sus _ids.
        Devuelve una lista de categorias.
        """
        if not category_ids:
            return []
        
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        
        object_ids = []
        for cid in category_ids:
            try:
                if isinstance(cid, ObjectId):
                    object_ids.append(cid)
                else:
                    object_ids.append(ObjectId(str(cid)))
            except Exception:
                continue
        
        if not object_ids:
            return []
        
        query = {"_id": {"$in": object_ids}, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("name", 1))

    # -------------------------------------------------------------
    #  BUSCAR POR NOMBRE
    # -------------------------------------------------------------
    @staticmethod
    def search_by_name(query: str, limit: int = 20, usuario_id=None):
        """
        Busca categorias cuyo nombre contenga el texto dado (case-insensitive).
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        
        if not query or not query.strip():
            return list(local_col.find(_uid_filter(usuario_id)).sort("name", 1).limit(limit))
        
        import re
        regex = re.compile(re.escape(query.strip()), re.IGNORECASE)
        search_query = {"name": {"$regex": regex}, **_uid_filter(usuario_id)}
        return list(local_col.find(search_query).sort("name", 1).limit(limit))

    # -------------------------------------------------------------
    #  ACTUALIZAR
    # -------------------------------------------------------------
    @staticmethod
    def update_category(category_id, name: str, usuario_id=None):
        """
        Actualiza el nombre de una categoria.
        Devuelve la categoria actualizada o None si no se encontro.
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id

        existing = local_col.find_one({
            "name": {"$regex": f"^{name}$", "$options": "i"},
            "_id": {"$ne": _id},
            **_uid_filter(usuario_id)
        })
        if existing:
            return None

        updates = {
            "name": name.strip(),
            "updated_at": datetime.utcnow()
        }

        query = {"_id": _id, **_uid_filter(usuario_id)}
        local_col.update_one(query, {"$set": updates})
        updated_category = local_col.find_one({"_id": _id})

        if updated_category:
            sync_to_remote(CategoryModel.COLLECTION, updated_category)
            print(f"Categoria {_id} actualizada: {name}")

        return updated_category

    # -------------------------------------------------------------
    #  ELIMINAR
    # -------------------------------------------------------------
    @staticmethod
    def delete_category(category_id, usuario_id=None):
        """
        Elimina una categoria tanto en la base local como remota.
        Devuelve True si se elimino, False si no se encontro.
        """
        local_col, remote_col = get_collection(CategoryModel.COLLECTION)

        try:
            _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        except Exception as e:
            print(f"Error al convertir category_id a ObjectId: {e}")
            return False

        query = {"_id": _id, **_uid_filter(usuario_id)}
        result = local_col.delete_one(query)
        deleted_locally = result.deleted_count > 0

        if deleted_locally:
            print(f"Categoria eliminada localmente: {_id}")

        if remote_col is not None:
            try:
                remote_col.delete_one(query)
                print(f"Categoria eliminada en remoto: {_id}")
            except Exception as e:
                print(f"Error al eliminar categoria de remoto (no crítico): {e}")

        return deleted_locally

    # -------------------------------------------------------------
    #  VERIFICAR SI EXISTE POR NOMBRE
    # -------------------------------------------------------------
    @staticmethod
    def exists_by_name(name: str, usuario_id=None) -> bool:
        """
        Verifica si existe una categoria con el nombre dado (case-insensitive).
        """
        local_col, _ = get_collection(CategoryModel.COLLECTION)
        existing = local_col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}, **_uid_filter(usuario_id)})
        return existing is not None

    # -------------------------------------------------------------
    #  CONTAR USO DE CATEGORIA
    # -------------------------------------------------------------
    @staticmethod
    def get_category_usage(category_id, usuario_id=None):
        """
        Cuenta cuántos objetivos, tareas y proyectos tienen asignada esta categoría.
        Devuelve un diccionario con los conteos.
        """
        try:
            _id = ObjectId(category_id) if not isinstance(category_id, ObjectId) else category_id
        except Exception:
            return {"goals": 0, "tasks": 0, "projects": 0, "total": 0}

        goals_col, _ = get_collection("Goals")
        tasks_col, _ = get_collection("Tasks")
        projects_col, _ = get_collection("Projects")

        uid_filter = _uid_filter(usuario_id)
        
        goals_count = goals_col.count_documents({"categorias": _id, **uid_filter})
        tasks_count = tasks_col.count_documents({"categorias": _id, **uid_filter})
        projects_count = projects_col.count_documents({"categorias": _id, **uid_filter})

        return {
            "goals": goals_count,
            "tasks": tasks_count,
            "projects": projects_count,
            "total": goals_count + tasks_count + projects_count
        }
